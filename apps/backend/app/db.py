"""Async MongoDB client singleton.

Reads MONGODB_URI and MONGODB_DB_NAME from the environment (loaded from the
service-local .env via python-dotenv). Never hardcode either value.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

_client: Optional[AsyncIOMotorClient] = None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Populate apps/backend/.env before running."
        )
    return value


def get_client() -> AsyncIOMotorClient:
    """Return the process-wide Motor client, creating it on first use."""
    global _client
    if _client is None:
        uri = _require_env("MONGODB_URI")
        _client = AsyncIOMotorClient(uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Return the configured database handle."""
    db_name = _require_env("MONGODB_DB_NAME")
    return get_client()[db_name]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
