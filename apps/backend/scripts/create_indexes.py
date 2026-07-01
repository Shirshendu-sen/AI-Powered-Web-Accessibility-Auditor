"""Create the indexes locked in Phase 1: violations.scan_id (asc),
scans.url, scans.scanned_at (desc). No speculative extras.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymongo

from app.db import close_client, get_db


async def create_indexes() -> None:
    db = get_db()
    await db.violations.create_index([("scan_id", pymongo.ASCENDING)])
    await db.scans.create_index([("url", pymongo.ASCENDING)])
    await db.scans.create_index([("scanned_at", pymongo.DESCENDING)])


async def main() -> int:
    await create_indexes()
    db = get_db()
    print("violations indexes:", list((await db.violations.index_information()).keys()))
    print("scans indexes:", list((await db.scans.index_information()).keys()))
    await close_client()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
