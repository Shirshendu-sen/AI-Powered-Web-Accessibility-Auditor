"""Runnable check for Phase 1 step 3: pings the real cluster."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running this script directly without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import close_client, get_client


async def main() -> int:
    client = get_client()
    result = await client.admin.command("ping")
    print(result)
    await close_client()
    return 0 if result.get("ok") == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
