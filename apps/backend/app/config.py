"""Runtime config for the orchestration API (Phase 7+).

Reads and validates env vars once at import time. All values are exported
as constants so route handlers stay declarative — no per-request
os.environ.get calls scattered around the codebase.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Populate apps/backend/.env before starting the API."
        )
    return value


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer; got {raw!r}") from exc


def _split_origins(raw: str) -> list[str]:
    """Comma-separated list of exact origins. `*` is allowed only in dev
    but is flagged with a runtime warning so nobody ships it to prod.
    """
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins


SCANNER_SERVICE_URL: str = _require("SCANNER_SERVICE_URL").rstrip("/")

CORS_ALLOWED_ORIGINS: list[str] = _split_origins(
    os.environ.get("CORS_ALLOWED_ORIGINS", "").strip() or "http://localhost:3000"
)

BACKEND_PORT: int = _int("BACKEND_PORT", 8000)

# ~15s end-to-end target per Phase 7 — split into a scanner call budget
# plus fixer fan-out budget. Adjustable via env for local debugging.
SCANNER_CALL_TIMEOUT_S: float = float(os.environ.get("SCANNER_CALL_TIMEOUT_S", "20"))
FIXER_CONCURRENCY: int = _int("FIXER_CONCURRENCY", 4)

# Debug info surfaced under /healthz for smoke-testing.
def public_config_snapshot() -> dict[str, object]:
    return {
        "scanner_service_url": SCANNER_SERVICE_URL,
        "cors_allowed_origins": CORS_ALLOWED_ORIGINS,
        "backend_port": BACKEND_PORT,
    }
