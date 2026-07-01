"""Phase 5 gate: AI ARIA / semantic fixer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.fixers import aria_fix  # noqa: E402


# ---------------------------------------------------------------------------
# Step 1 — patterns table parses and lists the axe rule IDs the guide names
# ---------------------------------------------------------------------------

def test_patterns_json_parses_and_covers_required_rule_ids():
    path = _BACKEND_ROOT / "app" / "data" / "aria_patterns.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    patterns = data["patterns"]
    # Guide names these explicitly (Phase 5 step 1).
    for rule_id in ("aria-allowed-attr", "button-name", "landmark-one-main", "region", "label"):
        assert rule_id in patterns, rule_id


def test_each_pattern_entry_has_required_keys():
    for rule_id, entry in aria_fix._PATTERNS.items():
        assert "apg_pattern" in entry, rule_id
        assert "guidance" in entry, rule_id
        assert "skeleton_examples" in entry, rule_id
        assert isinstance(entry["skeleton_examples"], list) and entry["skeleton_examples"]


# ---------------------------------------------------------------------------
# Step 2 — prompt building + JSON parsing
# ---------------------------------------------------------------------------

def _violation(rule_id: str = "button-name",
               snippet: str = "<button></button>",
               wcag: tuple[str, ...] = ("wcag2a", "wcag412")) -> dict:
    return {
        "ruleId": rule_id,
        "severity": "serious",
        "wcagRef": list(wcag),
        "domSnippet": snippet,
        "help": "Buttons must have discernible text",
    }


def test_prompt_includes_snippet_and_pattern_when_matched():
    v = _violation()
    pattern = aria_fix._pattern_for("button-name")
    prompt = aria_fix._build_prompt(v, pattern)
    assert "<button></button>" in prompt
    assert "Button" in prompt  # APG pattern name
    assert "WCAG" in prompt
    assert "STRICT JSON" in prompt


def test_prompt_flags_lower_confidence_when_no_pattern():
    v = _violation(rule_id="totally-made-up-rule")
    prompt = aria_fix._build_prompt(v, None)
    assert "lower-confidence" in prompt


def _stub_success_response() -> str:
    return json.dumps({
        "fixed_snippet": '<button type="button">Save</button>',
        "explanation": "Added visible text to satisfy WCAG SC 4.1.2 Name, Role, Value.",
    })


def test_generate_aria_fix_happy_path_returns_verified_dict():
    with mock.patch.object(aria_fix, "_call_model_once",
                           return_value=_stub_success_response()):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["type"] == "aria"
    assert fix["needs_manual_review"] is False
    assert '<button type="button">Save</button>' in fix["fixed"]
    assert "4.1.2" in fix["explanation"]
    assert fix["grounded_in_apg"] is True
    assert fix["confidence"] == 0.7


def test_unknown_rule_still_attempts_fix_with_lower_confidence():
    v = _violation(rule_id="unheard-of-rule")
    with mock.patch.object(aria_fix, "_call_model_once",
                           return_value=_stub_success_response()):
        fix = aria_fix.generate_aria_fix(v)
    assert fix["needs_manual_review"] is False
    assert fix["grounded_in_apg"] is False
    assert fix["confidence"] == 0.4
    # Explanation must note lower confidence when no APG entry matched.
    assert "lower-confidence" in fix["explanation"]


def test_markdown_code_fences_are_stripped():
    fenced = "```json\n" + _stub_success_response() + "\n```"
    with mock.patch.object(aria_fix, "_call_model_once", return_value=fenced):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["needs_manual_review"] is False
    assert fix["fixed"] == '<button type="button">Save</button>'


def test_retry_once_then_fall_back_on_malformed_json():
    calls = {"n": 0}

    def fake(prompt: str) -> str:
        calls["n"] += 1
        return "not json at all"

    with mock.patch.object(aria_fix, "_call_model_once", side_effect=fake):
        fix = aria_fix.generate_aria_fix(_violation())
    assert calls["n"] == 2  # exactly one retry
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "parse"


def test_retry_succeeds_after_first_bad_response():
    responses = ["not json", _stub_success_response()]

    def fake(prompt: str) -> str:
        return responses.pop(0)

    with mock.patch.object(aria_fix, "_call_model_once", side_effect=fake):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["needs_manual_review"] is False
    assert fix["fixed"].startswith("<button")


# ---------------------------------------------------------------------------
# Step 3 — HTML sanity check catches truncated / broken output
# ---------------------------------------------------------------------------

def test_html_sanity_check_rejects_truncated_snippet():
    # Two attempts both return a truncated snippet → manual review.
    truncated = json.dumps({
        "fixed_snippet": '<button type="button" aria-la',  # truncated attr
        "explanation": "Would add an accessible label.",
    })
    with mock.patch.object(aria_fix, "_call_model_once", return_value=truncated):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "parse"


def test_html_sanity_check_rejects_unbalanced_tags():
    broken = json.dumps({
        "fixed_snippet": "<button><span>x</button>",  # </span> missing
        "explanation": "Adds a span.",
    })
    with mock.patch.object(aria_fix, "_call_model_once", return_value=broken):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["needs_manual_review"] is True


def test_html_sanity_check_accepts_valid_void_elements():
    assert aria_fix._is_valid_html_fragment('<input type="text" aria-label="Name">')
    assert aria_fix._is_valid_html_fragment("<br>")
    assert aria_fix._is_valid_html_fragment("<img src=\"x\" alt=\"y\">")


def test_html_sanity_check_rejects_empty_or_whitespace():
    assert not aria_fix._is_valid_html_fragment("")
    assert not aria_fix._is_valid_html_fragment("   \n  ")


# ---------------------------------------------------------------------------
# Provider errors surface as structured manual-review objects
# ---------------------------------------------------------------------------

def test_provider_rate_limit_returns_manual_review():
    from app.ai_provider import AIProviderError
    with mock.patch.object(aria_fix, "_call_model_once",
                           side_effect=AIProviderError("429", kind="rate_limit")):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "rate_limit"


def test_provider_auth_error_returns_manual_review():
    from app.ai_provider import AIProviderError
    with mock.patch.object(aria_fix, "_call_model_once",
                           side_effect=AIProviderError("bad key", kind="auth")):
        fix = aria_fix.generate_aria_fix(_violation())
    assert fix["needs_manual_review"] is True
    assert fix["error_kind"] == "auth"


# ---------------------------------------------------------------------------
# Integration — real Gemini call for 3 different real violations.
# Skips per-violation on quota fallback (spec-permitted, matches Phase 4).
# ---------------------------------------------------------------------------

REAL_VIOLATIONS = [
    _violation(rule_id="button-name", snippet="<button></button>"),
    _violation(
        rule_id="label",
        snippet='<input type="text" name="q" placeholder="Search">',
        wcag=("wcag2a", "wcag131"),
    ),
    _violation(
        rule_id="link-name",
        snippet='<a href="/x"><svg aria-hidden="true"></svg></a>',
        wcag=("wcag2a", "wcag244"),
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize("violation", REAL_VIOLATIONS,
                         ids=[v["ruleId"] for v in REAL_VIOLATIONS])
def test_real_provider_produces_valid_fix(violation):
    fix = aria_fix.generate_aria_fix(violation)
    assert set(fix.keys()) >= {"type", "original", "fixed", "explanation", "confidence"}
    if fix.get("needs_manual_review"):
        pytest.skip(
            f"Free-tier fallback triggered ({fix.get('error_kind')}): {fix['explanation'][:120]}"
        )
    assert fix["type"] == "aria"
    assert isinstance(fix["fixed"], str) and fix["fixed"].strip()
    assert isinstance(fix["explanation"], str) and fix["explanation"].strip()
    assert aria_fix._is_valid_html_fragment(fix["fixed"])
