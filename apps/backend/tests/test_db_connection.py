"""Phase 1 gate: real Atlas roundtrip, no mocks.

Verifies:
  - db.command('ping') succeeds
  - Pydantic models accept a valid sample and reject a missing required field
  - insert/read/delete on all three collections leaves count deltas at zero
  - required indexes are present on scans and violations
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.db import close_client, get_db  # noqa: E402
from app.models import AiFix, Scan, User, Violation  # noqa: E402
from scripts.create_indexes import create_indexes  # noqa: E402


@pytest.fixture(scope="session")
def db():
    yield get_db()


@pytest.fixture(scope="session", autouse=True)
async def _close_motor_on_teardown():
    yield
    await close_client()


@pytest.mark.asyncio
async def test_ping(db):
    result = await db.command("ping")
    assert result.get("ok") == 1.0


def test_scan_model_valid_and_invalid():
    scan = Scan(
        url="https://example.com",
        scanned_at=datetime.now(timezone.utc),
        status="completed",
    )
    assert scan.url == "https://example.com"

    with pytest.raises(ValidationError):
        Scan(url="https://example.com", status="completed")  # scanned_at missing


def test_violation_model_valid_and_invalid():
    v = Violation(
        scan_id="abc",
        rule_id="color-contrast",
        severity="serious",
        wcag_ref=["wcag2aa"],
        dom_snippet="<a>x</a>",
        ai_fix=AiFix(type="contrast", original="#aaa", fixed="#000",
                     explanation="ok", confidence=1.0),
    )
    assert v.rule_id == "color-contrast"

    with pytest.raises(ValidationError):
        Violation(
            scan_id="abc",
            severity="serious",
            wcag_ref=["wcag2aa"],
            dom_snippet="<a>x</a>",
        )  # rule_id missing


def test_user_model_valid_and_invalid():
    u = User(
        email="a@b.co",
        password_hash="hash",
        created_at=datetime.now(timezone.utc),
    )
    assert u.email == "a@b.co"

    with pytest.raises(ValidationError):
        User(email="a@b.co", created_at=datetime.now(timezone.utc))  # password_hash missing


@pytest.mark.asyncio
async def test_indexes_exist(db):
    await create_indexes()
    scans_ix = await db.scans.index_information()
    violations_ix = await db.violations.index_information()

    def has_key(ix, field, direction):
        return any(
            key == [(field, direction)] for key in (v["key"] for v in ix.values())
        )

    assert has_key(scans_ix, "url", 1), scans_ix
    assert has_key(scans_ix, "scanned_at", -1), scans_ix
    assert has_key(violations_ix, "scan_id", 1), violations_ix


@pytest.mark.asyncio
async def test_roundtrip_leaves_no_orphans(db):
    """Insert, read back, delete — counts must be unchanged after."""
    marker = "phase1-test-" + datetime.now(timezone.utc).isoformat()

    counts_before = {
        "scans": await db.scans.count_documents({}),
        "violations": await db.violations.count_documents({}),
        "users": await db.users.count_documents({}),
    }

    scan_doc = {
        "url": marker,
        "scanned_at": datetime.now(timezone.utc),
        "status": "completed",
    }
    scan_res = await db.scans.insert_one(scan_doc)
    assert (await db.scans.find_one({"_id": scan_res.inserted_id})) is not None

    violation_doc = {
        "scan_id": scan_res.inserted_id,
        "rule_id": marker,
        "severity": "minor",
        "wcag_ref": ["wcag2aa"],
        "dom_snippet": "<x/>",
    }
    v_res = await db.violations.insert_one(violation_doc)
    assert (await db.violations.find_one({"_id": v_res.inserted_id})) is not None

    user_doc = {
        "email": marker + "@example.com",
        "password_hash": "notreal",
        "created_at": datetime.now(timezone.utc),
    }
    u_res = await db.users.insert_one(user_doc)
    assert (await db.users.find_one({"_id": u_res.inserted_id})) is not None

    await db.scans.delete_one({"_id": scan_res.inserted_id})
    await db.violations.delete_one({"_id": v_res.inserted_id})
    await db.users.delete_one({"_id": u_res.inserted_id})

    counts_after = {
        "scans": await db.scans.count_documents({}),
        "violations": await db.violations.count_documents({}),
        "users": await db.users.count_documents({}),
    }
    assert counts_after == counts_before, (counts_before, counts_after)
