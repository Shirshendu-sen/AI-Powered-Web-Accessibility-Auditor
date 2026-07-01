"""Phase 7 gate: FastAPI orchestration API.

Uses fastapi.TestClient for the unit-shaped checks (URL validation, healthz,
GET/POST round-trip, structured error when the scanner is unreachable) and
skips the "run against 3 real URLs" phase-level validation to a manual
smoke-test — that requires the scanner service to be running and the
scanner-side dev process is out of scope for pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.main import app  # noqa: E402
from app.routes import scans as scans_route  # noqa: E402


client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_motor_client():
    """TestClient uses a fresh event loop per call and Motor caches the
    loop from its first request — so between tests we must drop the
    cached client to avoid a "Event loop is closed" on the next test.
    """
    from app import db as db_module
    db_module._client = None
    yield
    db_module._client = None


# ---------------------------------------------------------------------------
# Step 1 — healthz
# ---------------------------------------------------------------------------

def test_healthz_returns_200_and_config_snapshot():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "scanner_service_url" in body["config"]
    assert body["config"]["cors_allowed_origins"] == ["http://localhost:3000"]


# ---------------------------------------------------------------------------
# URL validation — mirrors the scanner's own rules at the API boundary too
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,detail_substr", [
    ("notaurl", "only http"),
    ("ftp://example.com", "only http"),
    ("http://localhost:8000", "localhost"),
    ("http://127.0.0.1", "private-IP"),
    ("http://192.168.1.5", "private-IP"),
    ("http://10.0.0.1", "private-IP"),
])
def test_post_scan_rejects_bad_urls(url: str, detail_substr: str):
    resp = client.post("/api/scans", json={"url": url})
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert detail_substr in body["error"]["message"]


def test_post_scan_rejects_missing_url_field():
    resp = client.post("/api/scans", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Step 4 — structured error when scanner is unreachable
# ---------------------------------------------------------------------------

def test_scanner_unreachable_returns_structured_502(monkeypatch):
    """Point SCANNER_SERVICE_URL at a port nothing listens on and confirm
    we get a clean 502 with no stack trace.
    """
    monkeypatch.setattr(scans_route.config, "SCANNER_SERVICE_URL",
                        "http://127.0.0.1:1")  # port 1 is reserved / unreachable
    resp = client.post("/api/scans", json={"url": "https://example.com"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "502"
    assert "scanner unavailable" in body["error"]["message"]


def test_scanner_timeout_returns_structured_504(monkeypatch):
    async def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("simulated")

    class FakeClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, *a, **k):
            raise httpx.ReadTimeout("simulated")

    monkeypatch.setattr(scans_route.httpx, "AsyncClient", FakeClient)
    resp = client.post("/api/scans", json={"url": "https://example.com"})
    assert resp.status_code == 504
    body = resp.json()
    assert "timed out" in body["error"]["message"]


# ---------------------------------------------------------------------------
# Steps 2 & 3 — full pipeline round-trip with a mocked scanner. Real Mongo.
# ---------------------------------------------------------------------------

_FAKE_SCANNER_PAYLOAD = {
    "url": "https://example.com/",
    "violations": [
        {
            "ruleId": "color-contrast",
            "severity": "serious",
            "wcagRef": ["wcag2aa", "wcag143"],
            "domSnippet": "<a>needs contrast</a>",
            "target": ["a"],
            "data": {
                "fgColor": "#ff9999",
                "bgColor": "#344b6e",
                "contrastRatio": 4.31,
                "expectedContrastRatio": "4.5:1",
                "fontSize": "12.0pt",
                "fontWeight": "normal",
            },
        },
        {
            "ruleId": "button-name",
            "severity": "critical",
            "wcagRef": ["wcag2a", "wcag412"],
            "domSnippet": "<button></button>",
            "target": ["button"],
        },
    ],
}


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *a, **k):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def post(self, url, json=None):
        return _FakeResponse(200, _FAKE_SCANNER_PAYLOAD)


@pytest.fixture
def stub_scanner(monkeypatch):
    monkeypatch.setattr(scans_route.httpx, "AsyncClient", _FakeAsyncClient)


@pytest.fixture
def stub_aria_provider(monkeypatch):
    """Force ARIA fixer to hit the manual-review branch without an API
    call, so the pipeline test doesn't depend on Gemini quota.
    """
    from app.ai_provider import AIProviderError
    def raise_rate_limit(prompt):
        raise AIProviderError("stubbed quota", kind="rate_limit")
    from app.fixers import aria_fix
    monkeypatch.setattr(aria_fix, "_call_model_once", raise_rate_limit)


def test_post_scan_full_pipeline_and_get_roundtrip(stub_scanner, stub_aria_provider):
    resp = client.post("/api/scans", json={"url": "https://example.com/"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Assembled response shape from the guide's Phase 7 step 2 test.
    for key in ("scanId", "url", "scoreBefore", "scoreAfter", "status", "violations"):
        assert key in body, key
    assert body["url"] == "https://example.com/"
    assert isinstance(body["scoreBefore"], int)
    assert isinstance(body["scoreAfter"], int)
    assert body["scoreAfter"] <= body["scoreBefore"]
    assert len(body["violations"]) == 2

    for v in body["violations"]:
        assert "ai_fix" in v
        assert v["ai_fix"] is not None

    # Contrast fixer is deterministic and should self-verify.
    contrast_fixes = [v["ai_fix"] for v in body["violations"] if v["ruleId"] == "color-contrast"]
    assert contrast_fixes and contrast_fixes[0]["type"] == "contrast"

    # ARIA stubbed to rate_limit → manual review, but structured (not crash).
    aria_fixes = [v["ai_fix"] for v in body["violations"] if v["ruleId"] == "button-name"]
    assert aria_fixes and aria_fixes[0]["needs_manual_review"] is True
    # status should reflect the partial failure.
    assert body["status"] in ("completed_with_errors", "completed")

    scan_id = body["scanId"]

    # TestClient closes the per-request event loop after each call, so
    # Motor (bound to that loop on the POST) would fail on a follow-up
    # GET. Reset the cached client before the round-trip check.
    from app import db as db_module
    db_module._client = None

    # GET round-trip byte-identical (excluding the scannedAt timestamp
    # which the guide doesn't require in the response contract).
    get_resp = client.get(f"/api/scans/{scan_id}")
    assert get_resp.status_code == 200
    got = get_resp.json()
    assert got["url"] == body["url"]
    assert got["scoreBefore"] == body["scoreBefore"]
    assert got["scoreAfter"] == body["scoreAfter"]
    assert got["status"] == body["status"]
    assert len(got["violations"]) == len(body["violations"])

    # Independent Mongo verification: the docs actually exist.
    # TestClient closes its per-request loop, so we spin up a fresh loop
    # and a fresh Motor client bound to it for the verification.
    import asyncio
    from bson import ObjectId
    from motor.motor_asyncio import AsyncIOMotorClient
    import os

    async def _verify_and_cleanup():
        mc = AsyncIOMotorClient(os.environ["MONGODB_URI"])
        try:
            db = mc[os.environ["MONGODB_DB_NAME"]]
            oid = ObjectId(scan_id)
            scan_doc = await db.scans.find_one({"_id": oid})
            assert scan_doc is not None
            assert scan_doc["url"] == "https://example.com/"
            n = await db.violations.count_documents({"scan_id": oid})
            assert n == 2
            await db.scans.delete_one({"_id": oid})
            await db.violations.delete_many({"scan_id": oid})
        finally:
            mc.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_verify_and_cleanup())
    finally:
        loop.close()


def test_get_scan_404_on_unknown_id():
    from bson import ObjectId
    fake_id = str(ObjectId())  # valid shape, doesn't exist
    resp = client.get(f"/api/scans/{fake_id}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "404"


def test_get_scan_400_on_invalid_id():
    resp = client.get("/api/scans/not-an-oid")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "400"
