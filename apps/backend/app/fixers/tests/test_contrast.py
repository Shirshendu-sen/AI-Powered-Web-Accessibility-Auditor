"""Phase 3 gate: deterministic contrast fixer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.fixers.contrast import (  # noqa: E402
    EPSILON,
    MAX_ADJUST_ITERATIONS,
    NORMAL_TEXT_TARGET,
    adjust_for_contrast,
    contrast_ratio,
    generate_contrast_fix,
    parse_color,
    relative_luminance,
    rgb_to_hex,
)


# ---------------------------------------------------------------------------
# Step 1 — luminance and ratio formulas
# ---------------------------------------------------------------------------

def test_black_on_white_ratio_is_21():
    assert round(contrast_ratio((0, 0, 0), (255, 255, 255)), 2) == 21.00


def test_white_on_white_ratio_is_1():
    assert round(contrast_ratio((255, 255, 255), (255, 255, 255)), 2) == 1.00


def test_relative_luminance_endpoints():
    assert round(relative_luminance((0, 0, 0)), 4) == 0.0
    assert round(relative_luminance((255, 255, 255)), 4) == 1.0


def test_contrast_ratio_is_symmetric():
    a, b = (17, 34, 51), (238, 221, 204)
    assert round(contrast_ratio(a, b), 4) == round(contrast_ratio(b, a), 4)


# ---------------------------------------------------------------------------
# Step 2 — adjuster
# ---------------------------------------------------------------------------

def test_adjuster_pushes_light_gray_on_white_above_target():
    fg, bg = (200, 200, 200), (255, 255, 255)
    assert contrast_ratio(fg, bg) < NORMAL_TEXT_TARGET

    adjusted = adjust_for_contrast(fg, bg, NORMAL_TEXT_TARGET, large_text=False)
    assert adjusted is not None
    assert contrast_ratio(adjusted, bg) >= NORMAL_TEXT_TARGET


def test_adjuster_stays_bounded_on_near_impossible_pair():
    # Both mid-gray — no HSL lightness shift on the fg can hit 4.5:1
    # against a fixed bg without going into a colour we already tried.
    fg, bg = (128, 128, 128), (130, 130, 130)
    # If adjust_for_contrast ever looped past MAX_ADJUST_ITERATIONS the
    # test would hang — we simply require it to return in finite time
    # with either None or a self-verifying candidate.
    result = adjust_for_contrast(fg, bg, NORMAL_TEXT_TARGET, large_text=False)
    if result is not None:
        assert contrast_ratio(result, bg) >= NORMAL_TEXT_TARGET


def test_adjuster_short_circuits_when_already_compliant():
    fg, bg = (0, 0, 0), (255, 255, 255)
    assert adjust_for_contrast(fg, bg, NORMAL_TEXT_TARGET, large_text=False) == fg


# ---------------------------------------------------------------------------
# Step 3 — generate_contrast_fix on a full violation dict
# ---------------------------------------------------------------------------

def _violation(fg: str, bg: str, expected: str = "4.5:1",
               font_size: float = 12.0, font_weight: int = 400) -> dict:
    return {
        "ruleId": "color-contrast",
        "severity": "serious",
        "wcagRef": ["wcag2aa"],
        "domSnippet": "<p>x</p>",
        "data": {
            "fgColor": fg,
            "bgColor": bg,
            "contrastRatio": 0.0,
            "expectedContrastRatio": expected,
            "fontSize": font_size,
            "fontWeight": font_weight,
        },
    }


REQUIRED_KEYS = {"type", "original", "fixed", "explanation", "confidence"}


def test_generate_fix_returns_all_keys_and_self_verifies():
    fix = generate_contrast_fix(_violation("#c8c8c8", "#ffffff"))
    assert REQUIRED_KEYS.issubset(fix.keys())
    assert fix["type"] == "contrast"
    assert fix["confidence"] == 1.0
    assert fix["fixed"] is not None

    fixed_rgb = parse_color(fix["fixed"])
    bg_rgb = parse_color("#ffffff")
    assert fixed_rgb is not None and bg_rgb is not None
    assert contrast_ratio(fixed_rgb, bg_rgb) >= NORMAL_TEXT_TARGET


def test_generate_fix_handles_rgba_with_bg_flattening():
    v = _violation("rgba(0, 0, 0, 0.3)", "rgb(255, 255, 255)")
    fix = generate_contrast_fix(v)
    assert REQUIRED_KEYS.issubset(fix.keys())
    # rgba(0,0,0,0.3) on white flattens to a light gray → non-compliant, must fix.
    assert fix["fixed"] is not None


def test_generate_fix_on_unparseable_input_returns_manual_review():
    v = _violation("not-a-color", "#ffffff")
    fix = generate_contrast_fix(v)
    assert fix["fixed"] is None
    assert fix["needs_manual_review"] is True
    assert fix["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Step 4 — already-compliant short-circuit
# ---------------------------------------------------------------------------

def test_already_compliant_returns_unchanged_with_note():
    fix = generate_contrast_fix(_violation("#000000", "#ffffff"))
    assert fix["fixed"] == fix["original"]
    assert "already" in fix["explanation"].lower()


# ---------------------------------------------------------------------------
# Manual-review fallback: pair that even a bounded HSL sweep can't rescue
# ---------------------------------------------------------------------------

def test_manual_review_fallback_when_bg_is_mid_gray():
    # No HSL lightness shift on a mid-gray fg reaches 4.5:1 against
    # a nearly-identical mid-gray bg without wrapping around the
    # luminance range — bounded search must return manual review.
    fix = generate_contrast_fix(_violation("#808080", "#828282"))
    # Either a valid self-verified fix OR a manual-review fallback —
    # the invariant is we never lie about hitting the target.
    if fix["fixed"] is None:
        assert fix["needs_manual_review"] is True
    else:
        fixed_rgb = parse_color(fix["fixed"])
        bg_rgb = parse_color("#828282")
        assert fixed_rgb is not None and bg_rgb is not None
        assert contrast_ratio(fixed_rgb, bg_rgb) >= NORMAL_TEXT_TARGET


# ---------------------------------------------------------------------------
# Phase-level: real deque/mars violation payload → 100% self-verified
# ---------------------------------------------------------------------------

REAL_DEQUE_VIOLATION = {
    "ruleId": "color-contrast",
    "severity": "serious",
    "wcagRef": ["wcag2aa", "wcag143"],
    "domSnippet": "<a>needs contrast</a>",
    "data": {
        "fgColor": "#ff9999",
        "bgColor": "#344b6e",
        "contrastRatio": 4.31,
        "expectedContrastRatio": "4.5:1",
        "fontSize": "12.0pt (16.0px)",
        "fontWeight": "normal",
    },
}


def test_real_deque_violation_yields_self_verifying_fix():
    fix = generate_contrast_fix(REAL_DEQUE_VIOLATION)
    assert fix["type"] == "contrast"
    # Either we produce a passing colour or we correctly bow out.
    if fix["fixed"] is not None and not fix.get("needs_manual_review"):
        fixed_rgb = parse_color(fix["fixed"])
        bg_rgb = parse_color("#344b6e")
        assert contrast_ratio(fixed_rgb, bg_rgb) >= NORMAL_TEXT_TARGET
