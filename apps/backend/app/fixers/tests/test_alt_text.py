"""Phase 4 gate: AI alt-text fixer + ai_provider resolver."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import httpx
import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND_ROOT))

# Import will succeed here because AI_PROVIDER=gemini is set in .env, loaded
# by ai_provider.py at import time.
from app import ai_provider  # noqa: E402
from app.ai_provider import AIProviderError  # noqa: E402
from app.fixers import alt_text  # noqa: E402


# ---------------------------------------------------------------------------
# Step 3 — resolver import behaviour (must run in a subprocess because
# ai_provider raises at import time and once imported here it's cached).
# ---------------------------------------------------------------------------

_RESOLVER_CHECK_TEMPLATE = """\
import os, sys
sys.path.insert(0, r"{backend_root}")
{env_stmt}
import dotenv
import dotenv.main
def _noop(*a, **k):
    return False
dotenv.load_dotenv = _noop
dotenv.main.load_dotenv = _noop
try:
    from app import ai_provider  # noqa: F401
except Exception as exc:
    print("IMPORT_ERROR:", exc.__class__.__name__, str(exc)[:120])
    sys.exit(0)
print("NO_ERROR")
sys.exit(1)
"""


def _run_resolver_check(env_stmt: str, tmp_path: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "check.py"
    script.write_text(_RESOLVER_CHECK_TEMPLATE.format(
        backend_root=str(_BACKEND_ROOT), env_stmt=env_stmt,
    ), encoding="utf-8")
    env = os.environ.copy()
    env.pop("AI_PROVIDER", None)
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=30, env=env,
    )


def test_resolver_raises_on_unset_provider(tmp_path):
    proc = _run_resolver_check("os.environ.pop('AI_PROVIDER', None)", tmp_path)
    assert "IMPORT_ERROR" in proc.stdout, proc.stdout + proc.stderr


def test_resolver_raises_on_junk_provider(tmp_path):
    proc = _run_resolver_check("os.environ['AI_PROVIDER'] = 'chatgpt-plus'", tmp_path)
    assert "IMPORT_ERROR" in proc.stdout, proc.stdout + proc.stderr


def test_resolver_valid_provider_imports_cleanly():
    """The already-imported module should reflect the .env value."""
    assert ai_provider.AI_PROVIDER in ai_provider.VALID_PROVIDERS
    assert ai_provider.get_active_provider() == "gemini"


# ---------------------------------------------------------------------------
# Step 4 — generate_alt_text against a real image, using the configured
# provider. Skipped if the free-tier key hits a rate/quota/auth failure.
# ---------------------------------------------------------------------------

REAL_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Golden_Gate_Bridge_at_sunset_1.jpg/320px-Golden_Gate_Bridge_at_sunset_1.jpg"
REAL_CONTEXT = (
    "The Golden Gate Bridge stretches across the strait connecting San "
    "Francisco Bay and the Pacific Ocean, seen here in the late-afternoon light."
)


@pytest.mark.integration
def test_real_provider_call_produces_valid_alt_text():
    fix = alt_text.generate_alt_text(REAL_IMAGE_URL, REAL_CONTEXT, max_length=125)
    # If the free-tier key is rate-limited, invalid, or the network is
    # unavailable, the fixer returns a manual-review object with an
    # error_kind. We don't fail the test for that — the fallback IS the
    # spec — but we do assert the shape is correct and log what happened.
    assert set(fix.keys()) >= {"type", "original", "fixed", "explanation", "confidence"}
    if fix.get("needs_manual_review"):
        pytest.skip(f"Free-tier fallback triggered ({fix.get('error_kind')}): {fix['explanation']}")
    assert fix["type"] == "alt_text"
    assert isinstance(fix["fixed"], str) and 0 < len(fix["fixed"]) <= 125
    lower = fix["fixed"].lower()
    for banned in ("image of ", "picture of ", "photo of ", "graphic of "):
        assert not lower.startswith(banned), fix["fixed"]


# ---------------------------------------------------------------------------
# Step 5 — all failure paths degrade gracefully
# ---------------------------------------------------------------------------

def test_bad_url_returns_manual_review():
    fix = alt_text.generate_alt_text("not-a-url", "any", max_length=125)
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "fetch"


def test_http_404_returns_manual_review():
    # A URL that reliably 404s on a well-known host.
    fix = alt_text.generate_alt_text(
        "https://httpbin.org/status/404",
        "context",
        max_length=125,
    )
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "fetch"


def test_wrong_content_type_returns_manual_review():
    with mock.patch("app.fixers.alt_text.httpx.stream") as m:
        cm = mock.MagicMock()
        cm.__enter__.return_value.status_code = 200
        cm.__enter__.return_value.headers = {"content-type": "text/html"}
        cm.__enter__.return_value.iter_bytes.return_value = iter([b"<html/>"])
        m.return_value = cm
        fix = alt_text.generate_alt_text("https://example.com/x", "c", max_length=125)
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "fetch"


def test_provider_auth_error_returns_manual_review():
    with mock.patch("app.fixers.alt_text._fetch_image", return_value=(b"\x89PNG", "image/png")):
        with mock.patch("app.fixers.alt_text.ai_provider.generate_vision",
                        side_effect=AIProviderError("bad key", kind="auth")):
            fix = alt_text.generate_alt_text("https://x/img.png", "c", max_length=125)
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "auth"


def test_provider_rate_limit_returns_manual_review():
    with mock.patch("app.fixers.alt_text._fetch_image", return_value=(b"\x89PNG", "image/png")):
        with mock.patch("app.fixers.alt_text.ai_provider.generate_vision",
                        side_effect=AIProviderError("429 quota", kind="rate_limit")):
            fix = alt_text.generate_alt_text("https://x/img.png", "c", max_length=125)
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "rate_limit"


def test_provider_timeout_returns_manual_review():
    with mock.patch("app.fixers.alt_text._fetch_image", return_value=(b"\x89PNG", "image/png")):
        with mock.patch("app.fixers.alt_text.ai_provider.generate_vision",
                        side_effect=AIProviderError("timeout", kind="timeout")):
            fix = alt_text.generate_alt_text("https://x/img.png", "c", max_length=125)
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "timeout"


# ---------------------------------------------------------------------------
# Step 6 — MAX_IMAGES_PER_SCAN cap verified by call count
# ---------------------------------------------------------------------------

def test_max_images_per_scan_cap_by_call_count(monkeypatch):
    monkeypatch.setenv("MAX_IMAGES_PER_SCAN", "3")
    call_count = {"n": 0}

    def fake_generator(url, ctx, max_length):
        call_count["n"] += 1
        return {
            "type": "alt_text",
            "original": url,
            "fixed": "alt",
            "explanation": "stub",
            "confidence": 0.7,
            "needs_manual_review": False,
        }

    violations = [
        {"ruleId": "image-alt",
         "context": {"src": f"https://example.com/i{i}.png", "surrounding": "c"}}
        for i in range(7)
    ]

    results = alt_text.process_alt_text_violations(
        violations, _generator=fake_generator,
    )

    assert len(results) == 7
    assert call_count["n"] == 3, (
        f"expected exactly 3 generator calls; got {call_count['n']}"
    )
    capped = [r for r in results if r["ai_fix"].get("error_kind") == "capped"]
    assert len(capped) == 4
    for r in capped:
        assert r["ai_fix"]["needs_manual_review"] is True
        assert "image cap reached" in r["ai_fix"]["explanation"]


def test_decorative_image_skipped_without_provider_call(monkeypatch):
    monkeypatch.setenv("MAX_IMAGES_PER_SCAN", "5")
    calls = {"n": 0}

    def fake_generator(*args, **kwargs):
        calls["n"] += 1
        return {"type": "alt_text", "original": "x", "fixed": "y",
                "explanation": "", "confidence": 0.7, "needs_manual_review": False}

    violations = [
        {"ruleId": "image-alt",
         "context": {"src": "https://example.com/spacer.png",
                     "surrounding": "", "role": "presentation",
                     "width": 1, "height": 1}},
        {"ruleId": "image-alt",
         "context": {"src": "https://example.com/tiny.png",
                     "surrounding": "", "role": "",
                     "width": 4, "height": 4}},
    ]
    results = alt_text.process_alt_text_violations(
        violations, _generator=fake_generator,
    )
    assert calls["n"] == 0
    for r in results:
        assert r["ai_fix"]["fixed"] == ""
        assert r["ai_fix"]["needs_manual_review"] is False
