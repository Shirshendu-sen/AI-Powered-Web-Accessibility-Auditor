"""Phase 6 gate: severity-weighted scoring engine.

Uses the "verified-only" score_after semantics chosen at build time.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.db import close_client, get_db  # noqa: E402
from app.scoring import (  # noqa: E402
    SEVERITY_WEIGHTS,
    compute_before_after,
    compute_score,
)


# ---------------------------------------------------------------------------
# Step 1 — weight table and compute_score
# ---------------------------------------------------------------------------

def test_weights_match_locked_spec_exactly():
    # Locked in Section 2.5 — never adjust without approval.
    assert SEVERITY_WEIGHTS == {
        "critical": 10, "serious": 7, "moderate": 4, "minor": 2,
    }


def test_compute_score_matches_hand_calculated_total():
    violations = [
        {"severity": "critical"},   # 10
        {"severity": "serious"},    #  7
        {"severity": "moderate"},   #  4
        {"severity": "minor"},      #  2
        {"severity": "moderate"},   #  4
    ]
    # 10 + 7 + 4 + 2 + 4 = 27
    assert compute_score(violations) == 27


def test_compute_score_empty_list_is_zero():
    assert compute_score([]) == 0


# ---------------------------------------------------------------------------
# Step 2 — compute_before_after with verified-only semantics
# ---------------------------------------------------------------------------

def _verified_fix() -> dict:
    return {"type": "contrast", "fixed": "#000000",
            "explanation": "ok", "confidence": 1.0,
            "needs_manual_review": False}


def _manual_review_fix() -> dict:
    return {"type": "aria", "fixed": None,
            "explanation": "provider error", "confidence": 0.0,
            "needs_manual_review": True, "error_kind": "rate_limit"}


def test_2_of_5_verified_after_equals_remaining_3_weight_sum():
    # Weights: 10 + 7 + 4 + 2 + 10 = 33
    # Verified fixes on items 0 and 2 → after = 7 + 2 + 10 = 19
    violations_with_fixes = [
        {"severity": "critical", "ai_fix": _verified_fix()},        # dropped
        {"severity": "serious",  "ai_fix": _manual_review_fix()},   # kept
        {"severity": "moderate", "ai_fix": _verified_fix()},        # dropped
        {"severity": "minor",    "ai_fix": _manual_review_fix()},   # kept
        {"severity": "critical", "ai_fix": _manual_review_fix()},   # kept
    ]
    before, after = compute_before_after(violations_with_fixes)
    assert before == 33
    assert after == 19


def test_all_fixes_verified_yields_zero_after():
    items = [
        {"severity": "critical", "ai_fix": _verified_fix()},
        {"severity": "serious",  "ai_fix": _verified_fix()},
    ]
    before, after = compute_before_after(items)
    assert before == 17 and after == 0


def test_no_fixes_verified_yields_after_equal_before():
    items = [
        {"severity": "critical", "ai_fix": _manual_review_fix()},
        {"severity": "moderate", "ai_fix": None},
        {"severity": "minor",    "ai_fix": _manual_review_fix()},
    ]
    before, after = compute_before_after(items)
    assert before == 16 and after == 16


def test_wrapper_shape_from_alt_text_processor_is_supported():
    """process_alt_text_violations returns {"violation": v, "ai_fix": f}."""
    items = [
        {"violation": {"severity": "serious"}, "ai_fix": _verified_fix()},
        {"violation": {"severity": "moderate"}, "ai_fix": _manual_review_fix()},
    ]
    before, after = compute_before_after(items)
    assert before == 11 and after == 4


def test_score_after_never_exceeds_score_before_invariant():
    items = [{"severity": "critical", "ai_fix": _verified_fix()}]
    before, after = compute_before_after(items)
    assert after <= before


def test_unknown_severity_scores_zero_and_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app.scoring"):
        total = compute_score([
            {"severity": "info"},
            {"severity": "critical"},
        ])
    assert total == 10
    assert any("unknown severity" in r.message for r in caplog.records)


def test_missing_severity_field_does_not_crash():
    # e.g., malformed violation dict — scoring must degrade to 0 for that item.
    total = compute_score([{"ruleId": "x"}, {"severity": "serious"}])
    assert total == 7


def test_empty_alt_for_decorative_image_counts_as_verified():
    """alt_text fixer returns fixed="" for decorative images with
    needs_manual_review=False — that must count as verified.
    """
    decorative = {
        "type": "alt_text", "fixed": "", "explanation": "decorative",
        "confidence": 0.9, "needs_manual_review": False,
    }
    items = [{"severity": "serious", "ai_fix": decorative}]
    before, after = compute_before_after(items)
    assert before == 7 and after == 0


# ---------------------------------------------------------------------------
# Step 3 — persist score_before / score_after onto scans, round-trip Mongo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scores_round_trip_through_mongodb():
    db = get_db()

    items = [
        {"severity": "critical", "ai_fix": _verified_fix()},
        {"severity": "serious",  "ai_fix": _manual_review_fix()},
    ]
    before, after = compute_before_after(items)

    scan_doc = {
        "url": "phase6-test",
        "scanned_at": datetime.now(timezone.utc),
        "score_before": before,
        "score_after": after,
        "status": "completed",
    }
    res = await db.scans.insert_one(scan_doc)
    try:
        readback = await db.scans.find_one({"_id": res.inserted_id})
        assert readback is not None
        # Exact schema field names per Section 2.3.
        assert readback["score_before"] == before
        assert readback["score_after"] == after
        assert isinstance(readback["score_before"], int)
        assert isinstance(readback["score_after"], int)
    finally:
        await db.scans.delete_one({"_id": res.inserted_id})


@pytest.fixture(scope="session", autouse=True)
async def _close_motor_on_teardown():
    yield
    await close_client()
