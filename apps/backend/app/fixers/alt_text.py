"""AI-generated alt-text for image-alt violations (Phase 4).

Never fabricates a description — the fixer only calls the provider with an
actual fetched image plus real surrounding-text context. Any failure mode
(fetch fail, bad content-type, timeout, auth reject, rate limit) is
returned as a "needs manual review" ai_fix so the pipeline never crashes.

Callers must invoke `process_alt_text_violations` for a full scan so the
MAX_IMAGES_PER_SCAN cap is enforced (per-scan counter). `generate_alt_text`
handles a single image and does not know the cap.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx
from dotenv import load_dotenv

from app import ai_provider
from app.ai_provider import AIProviderError

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_ROOT / ".env")

log = logging.getLogger(__name__)

MAX_LENGTH_DEFAULT = 125
IMAGE_FETCH_TIMEOUT_S = 10.0
IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

_ALLOWED_MIME_PREFIXES = ("image/",)
_ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
}

# Guidance banned by the guide — the model should not open with "image of…".
_BANNED_PREFIXES = (
    "image of ",
    "picture of ",
    "photo of ",
    "graphic of ",
    "illustration of ",
    "photograph of ",
)


def _max_images_per_scan() -> int:
    raw = os.environ.get("MAX_IMAGES_PER_SCAN", "5").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 5
    return max(0, n)


def _prompt(surrounding_text: str, max_length: int) -> str:
    context = (surrounding_text or "").strip()
    context_block = context[:500] if context else "(no surrounding text available)"
    return (
        "You are writing HTML alt text for an image on a real web page. "
        f"Write a concise, contextual description in at most {max_length} "
        "characters. Do NOT start with phrases like 'image of', 'picture of', "
        "'photo of', or 'graphic of'. Do NOT add quotes. Return only the alt "
        "text itself — no explanation, no markdown.\n\n"
        f"Surrounding page text for context:\n{context_block}"
    )


def _clean(text: str, max_length: int) -> str:
    t = text.strip().strip('"').strip("'")
    t = re.sub(r"^alt\s*[:=]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t)
    for banned in _BANNED_PREFIXES:
        if t.lower().startswith(banned):
            t = t[len(banned):]
            break
    if len(t) > max_length:
        cut = t[:max_length].rsplit(" ", 1)
        t = (cut[0] if cut and cut[0] else t[:max_length]).rstrip(",.;:!?-")
    return t.strip()


def _decorative(context: Optional[dict[str, Any]]) -> Optional[str]:
    """Return a short reason if the image is clearly decorative and should
    be handled as an empty-alt marker rather than an AI call.
    """
    if not context:
        return None
    if context.get("role") == "presentation" or context.get("role") == "none":
        return "role=\"presentation\""
    try:
        w = int(str(context.get("width") or 0))
        h = int(str(context.get("height") or 0))
    except (TypeError, ValueError):
        w = h = 0
    if 0 < w <= 8 and 0 < h <= 8:
        return f"tiny image ({w}x{h}) — likely decorative"
    return None


def _manual_review(original: str, explanation: str, *, error_kind: Optional[str] = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "alt_text",
        "original": original,
        "fixed": None,
        "explanation": explanation,
        "confidence": 0.0,
        "needs_manual_review": True,
    }
    if error_kind:
        entry["error_kind"] = error_kind
    return entry


def _fetch_image(url: str) -> tuple[bytes, str]:
    """Fetch an image with a timeout, size cap, and content-type check.

    Raises AIProviderError-like RuntimeError subclasses on any failure so
    generate_alt_text can convert them into a manual-review response.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError(f"image url must be absolute http(s); got {url!r}")

    with httpx.stream(
        "GET",
        url,
        timeout=IMAGE_FETCH_TIMEOUT_S,
        follow_redirects=True,
        headers={
            "User-Agent": "AccessibilityAuditor/1.0 (server-side image fetch)",
            "Accept": "image/*",
        },
    ) as resp:
        if resp.status_code >= 400:
            raise RuntimeError(f"image fetch returned HTTP {resp.status_code}")

        content_type = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if not any(content_type.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
            raise RuntimeError(f"unsupported content-type: {content_type!r}")
        if content_type not in _ALLOWED_MIME_TYPES:
            # e.g. image/svg+xml — Gemini and OpenRouter vision APIs may
            # accept SVG in some models but reject it in others; be
            # conservative for the free-tier path.
            raise RuntimeError(f"unsupported image format: {content_type!r}")

        buf = bytearray()
        for chunk in resp.iter_bytes():
            buf.extend(chunk)
            if len(buf) > IMAGE_MAX_BYTES:
                raise RuntimeError(f"image exceeds {IMAGE_MAX_BYTES} byte cap")
        return bytes(buf), content_type


def generate_alt_text(
    image_url: str,
    surrounding_text: str,
    max_length: int = MAX_LENGTH_DEFAULT,
) -> dict[str, Any]:
    """Generate contextual alt text for a single image URL.

    Returns an ai_fix-shaped dict. Every failure path degrades to a
    manual-review object — never raises to the caller.
    """
    try:
        image_bytes, mime = _fetch_image(image_url)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.warning("alt_text: image fetch failed for %s: %s", image_url, exc)
        return _manual_review(image_url, f"Image fetch failed: {exc}", error_kind="fetch")
    except (ValueError, RuntimeError) as exc:
        log.warning("alt_text: image rejected for %s: %s", image_url, exc)
        return _manual_review(image_url, f"Image rejected: {exc}", error_kind="fetch")

    prompt = _prompt(surrounding_text, max_length)
    try:
        raw = ai_provider.generate_vision(image_bytes, mime, prompt)
    except AIProviderError as exc:
        log.warning("alt_text: provider %s error for %s: %s", exc.kind, image_url, exc)
        return _manual_review(
            image_url,
            f"AI provider {exc.kind}: {exc}. "
            "Free-tier keys hit rate/quota limits during normal use — "
            "switch AI_PROVIDER or wait for the quota window and re-run.",
            error_kind=exc.kind,
        )
    except Exception as exc:  # noqa: BLE001 — defensive: never crash the pipeline
        log.exception("alt_text: unexpected provider error for %s", image_url)
        return _manual_review(image_url, f"Unexpected provider error: {exc}", error_kind="upstream")

    alt = _clean(raw, max_length)
    if not alt:
        return _manual_review(image_url, "Model returned an empty response.", error_kind="upstream")

    return {
        "type": "alt_text",
        "original": image_url,
        "fixed": alt,
        "explanation": f"Generated with {ai_provider.get_active_provider()} using image + surrounding text context.",
        "confidence": 0.7,
        "needs_manual_review": False,
    }


def process_alt_text_violations(
    violations: Iterable[dict[str, Any]],
    max_length: int = MAX_LENGTH_DEFAULT,
    _generator=generate_alt_text,  # test hook so we can spy on call count
) -> list[dict[str, Any]]:
    """Enforce MAX_IMAGES_PER_SCAN — anything beyond the cap gets the
    skipped marker rather than being silently dropped.
    """
    cap = _max_images_per_scan()
    processed_count = 0
    out: list[dict[str, Any]] = []

    for v in violations:
        context = v.get("context") if isinstance(v, dict) else None
        image_url = (context or {}).get("src") if context else None
        surrounding = (context or {}).get("surrounding", "") if context else ""

        if not image_url:
            out.append({
                "violation": v,
                "ai_fix": _manual_review(
                    "(no image url)",
                    "Scanner did not resolve an image src; needs manual review.",
                    error_kind="fetch",
                ),
            })
            continue

        decorative_reason = _decorative(context)
        if decorative_reason:
            out.append({
                "violation": v,
                "ai_fix": {
                    "type": "alt_text",
                    "original": image_url,
                    "fixed": "",
                    "explanation": (
                        f"Marked as decorative ({decorative_reason}); the correct fix "
                        "is empty alt=\"\" plus role=\"presentation\" if not already set."
                    ),
                    "confidence": 0.9,
                    "needs_manual_review": False,
                },
            })
            continue

        if processed_count >= cap:
            out.append({
                "violation": v,
                "ai_fix": {
                    "type": "alt_text",
                    "original": image_url,
                    "fixed": None,
                    "explanation": (
                        f"Skipped — manual review (image cap reached: "
                        f"MAX_IMAGES_PER_SCAN={cap})."
                    ),
                    "confidence": 0.0,
                    "needs_manual_review": True,
                    "error_kind": "capped",
                },
            })
            continue

        processed_count += 1
        out.append({"violation": v, "ai_fix": _generator(image_url, surrounding, max_length)})

    return out
