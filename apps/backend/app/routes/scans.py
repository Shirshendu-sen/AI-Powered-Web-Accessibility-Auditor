"""POST /api/scans and GET /api/scans/{id} — the single public REST
contract the frontend calls (Phase 7).

Flow for POST:
  1. Validate URL (reject non-http(s), localhost, private IPs — scanner
     enforces the same thing but the API rejects at the boundary too).
  2. Call the scanner over HTTP (SCANNER_SERVICE_URL).
  3. For each violation, dispatch to its matching fixer with a bounded
     semaphore. Per-violation try/except — one fixer crash never aborts
     the scan; it downgrades that single violation to manual review.
  4. Compute score_before / score_after (Phase 6, verified-only).
  5. Persist scans + violations documents (Phase 1).
  6. Return the assembled JSON.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.db import get_db
from app.fixers.alt_text import (
    MAX_LENGTH_DEFAULT as ALT_TEXT_MAX_LENGTH,
    _decorative,
    _max_images_per_scan,
    generate_alt_text,
)
from app.fixers.aria_fix import generate_aria_fix
from app.fixers.contrast import generate_contrast_fix
from app.scoring import compute_before_after

log = logging.getLogger("app.routes.scans")
router = APIRouter()

_CONTRAST_RULES = {"color-contrast", "color-contrast-enhanced"}
_IMAGE_ALT_RULES = {"image-alt", "role-img-alt", "svg-img-alt",
                    "input-image-alt", "area-alt"}


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class FixOut(BaseModel):
    type: str
    original: Optional[str] = None
    fixed: Optional[str] = None
    explanation: str
    confidence: float
    needs_manual_review: bool = False


class ViolationOut(BaseModel):
    ruleId: str
    severity: str
    wcagRef: list[str] = Field(default_factory=list)
    domSnippet: str
    ai_fix: Optional[dict[str, Any]] = None


class ScanResponse(BaseModel):
    scanId: str
    url: str
    scoreBefore: int
    scoreAfter: int
    status: str
    violations: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_url(raw: str) -> str:
    try:
        parsed = urlparse(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="url is not a valid URL")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="only http and https URLs are allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="url has no host")
    if host in ("localhost", "0.0.0.0") or host.endswith(".localhost"):
        raise HTTPException(status_code=400, detail="localhost targets are not allowed")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(status_code=400, detail="private-IP targets are not allowed")
    except ValueError:
        pass  # hostname, not an IP literal — fine
    return raw


async def _call_scanner(url: str) -> list[dict[str, Any]]:
    """POST to the scanner service and return its violations array.

    Distinguishes scanner-unavailable (502) from scanner-error (bubbles up).
    """
    endpoint = f"{config.SCANNER_SERVICE_URL}/scan"
    try:
        async with httpx.AsyncClient(timeout=config.SCANNER_CALL_TIMEOUT_S) as client:
            resp = await client.post(endpoint, json={"url": url})
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise HTTPException(status_code=502,
                            detail=f"scanner unavailable: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,
                            detail=f"scanner timed out after {config.SCANNER_CALL_TIMEOUT_S}s") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,
                            detail=f"scanner upstream error: {exc}") from exc

    if resp.status_code >= 400:
        # Bubble scanner-side validation and 429s up as 4xx so the client
        # sees the right category.
        raise HTTPException(status_code=resp.status_code,
                            detail=f"scanner returned {resp.status_code}: {resp.text[:200]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502,
                            detail=f"scanner returned invalid JSON: {exc}") from exc
    violations = payload.get("violations")
    if not isinstance(violations, list):
        raise HTTPException(status_code=502, detail="scanner response missing violations[]")
    return violations


def _default_manual_review(rule_id: str, severity: str, reason: str) -> dict[str, Any]:
    return {
        "type": "manual",
        "original": None,
        "fixed": None,
        "explanation": reason,
        "confidence": 0.0,
        "needs_manual_review": True,
        "grounded_in_apg": False,
    }


def _sync_fix_for_violation(violation: dict[str, Any]) -> dict[str, Any]:
    """Run the synchronous fixers (contrast, aria) for one violation.
    Never raises — every failure downgrades to manual review.
    """
    rule_id = str(violation.get("ruleId", ""))
    try:
        if rule_id in _CONTRAST_RULES:
            return generate_contrast_fix(violation)
        # Everything else that isn't image-alt (handled separately) goes to ARIA.
        return generate_aria_fix(violation)
    except Exception as exc:  # noqa: BLE001 — never abort the scan
        log.exception("fixer crashed for rule=%s", rule_id)
        return _default_manual_review(
            rule_id,
            violation.get("severity", "minor"),
            f"Fixer crashed: {exc}",
        )


async def _fan_out_fixers(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach an ai_fix to every violation.

    Image-alt violations run through the async, capped alt-text pipeline
    (MAX_IMAGES_PER_SCAN enforced here at the orchestration layer, not
    only inside Phase 4). Every other rule runs on a thread pool with a
    bounded semaphore.
    """
    image_alt_indexes: list[int] = []
    other_indexes: list[int] = []
    for i, v in enumerate(violations):
        rule_id = str(v.get("ruleId", ""))
        if rule_id in _IMAGE_ALT_RULES:
            image_alt_indexes.append(i)
        else:
            other_indexes.append(i)

    semaphore = asyncio.Semaphore(config.FIXER_CONCURRENCY)

    async def run_sync(idx: int) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            fix = await asyncio.to_thread(_sync_fix_for_violation, violations[idx])
            return idx, fix

    async def run_alt(idx: int, *, spend: bool) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            v = violations[idx]
            ctx = v.get("context") or {}
            src = ctx.get("src")
            surrounding = ctx.get("surrounding", "") if ctx else ""

            if not src:
                return idx, _default_manual_review(
                    v.get("ruleId", ""), v.get("severity", "minor"),
                    "Scanner did not resolve an image src; needs manual review.",
                )
            decorative_reason = _decorative(ctx)
            if decorative_reason:
                return idx, {
                    "type": "alt_text",
                    "original": src,
                    "fixed": "",
                    "explanation": (
                        f"Marked as decorative ({decorative_reason}); the correct "
                        "fix is empty alt=\"\" plus role=\"presentation\" if not "
                        "already set."
                    ),
                    "confidence": 0.9,
                    "needs_manual_review": False,
                }
            if not spend:
                cap = _max_images_per_scan()
                return idx, {
                    "type": "alt_text",
                    "original": src,
                    "fixed": None,
                    "explanation": (
                        f"Skipped — manual review (image cap reached: "
                        f"MAX_IMAGES_PER_SCAN={cap})."
                    ),
                    "confidence": 0.0,
                    "needs_manual_review": True,
                    "error_kind": "capped",
                }
            try:
                fix = await asyncio.to_thread(
                    generate_alt_text, src, surrounding, ALT_TEXT_MAX_LENGTH,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("alt_text fixer crashed for %s", src)
                fix = _default_manual_review(
                    v.get("ruleId", ""), v.get("severity", "minor"),
                    f"Alt-text fixer crashed: {exc}",
                )
            return idx, fix

    tasks = [run_sync(i) for i in other_indexes]
    cap = _max_images_per_scan()
    for pos, i in enumerate(image_alt_indexes):
        tasks.append(run_alt(i, spend=pos < cap))

    results = await asyncio.gather(*tasks)

    out = [dict(v) for v in violations]
    for idx, fix in results:
        out[idx]["ai_fix"] = fix
    return out


def _summarize_status(fixes: list[dict[str, Any]]) -> str:
    if not fixes:
        return "completed"
    manual = sum(1 for f in fixes
                 if isinstance(f.get("ai_fix"), dict)
                 and f["ai_fix"].get("needs_manual_review"))
    if manual == 0:
        return "completed"
    if manual == len(fixes):
        return "completed_with_errors"
    return "completed_with_errors"


def _serialize_scan(doc: dict[str, Any], violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scanId": str(doc["_id"]),
        "url": doc["url"],
        "scoreBefore": int(doc["score_before"]),
        "scoreAfter": int(doc["score_after"]),
        "status": doc["status"],
        "scannedAt": doc["scanned_at"].isoformat(),
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/scans")
async def create_scan(body: ScanRequest):
    url = _validate_url(body.url)

    raw_violations = await _call_scanner(url)
    with_fixes = await _fan_out_fixers(raw_violations)

    before, after = compute_before_after(with_fixes)
    status = _summarize_status(with_fixes)

    db = get_db()
    scanned_at = datetime.now(timezone.utc)
    scan_doc = {
        "url": url,
        "scanned_at": scanned_at,
        "score_before": before,
        "score_after": after,
        "status": status,
    }
    scan_result = await db.scans.insert_one(scan_doc)
    scan_id = scan_result.inserted_id

    if with_fixes:
        docs = []
        for v in with_fixes:
            doc = {
                "scan_id": scan_id,
                "rule_id": v.get("ruleId", ""),
                "severity": v.get("severity", "minor"),
                "wcag_ref": v.get("wcagRef", []),
                "dom_snippet": v.get("domSnippet", ""),
                "ai_fix": v.get("ai_fix"),
            }
            docs.append(doc)
        await db.violations.insert_many(docs)

    saved = {**scan_doc, "_id": scan_id}
    return _serialize_scan(saved, with_fixes)


@router.get("/scans/{scan_id}")
async def read_scan(scan_id: str):
    try:
        oid = ObjectId(scan_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="invalid scan id") from exc

    db = get_db()
    scan_doc = await db.scans.find_one({"_id": oid})
    if not scan_doc:
        raise HTTPException(status_code=404, detail="scan not found")

    cursor = db.violations.find({"scan_id": oid})
    violations = []
    async for v in cursor:
        violations.append({
            "ruleId": v.get("rule_id", ""),
            "severity": v.get("severity", "minor"),
            "wcagRef": v.get("wcag_ref", []),
            "domSnippet": v.get("dom_snippet", ""),
            "ai_fix": v.get("ai_fix"),
        })
    return _serialize_scan(scan_doc, violations)
