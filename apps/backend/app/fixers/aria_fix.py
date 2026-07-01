"""AI-generated ARIA / semantic fix (Phase 5).

Grounded in the APG pattern table (app/data/aria_patterns.json) — never
invents an attribute or role. If the model returns markdown code fences,
malformed JSON, or HTML that can't be parsed, we retry once and then fall
back to a manual-review object. The output diff is capped to the smallest
change that resolves the cited violation; unrelated refactors are rejected
in the prompt itself.

Uses the shared provider resolver from app.ai_provider — this fixer does
NOT import a provider SDK directly (per guide Section 3.1).
"""

from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional

from app import ai_provider
from app.ai_provider import AIProviderError

log = logging.getLogger(__name__)

_PATTERNS_PATH = Path(__file__).resolve().parent.parent / "data" / "aria_patterns.json"
_MAX_SNIPPET_CHARS = 800
_FENCE_RE = re.compile(r"^```(?:json|html)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _load_patterns() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_PATTERNS_PATH.read_text(encoding="utf-8"))
        return data.get("patterns", {})
    except (OSError, json.JSONDecodeError) as exc:
        log.error("aria_fix: failed to load patterns: %s", exc)
        return {}


_PATTERNS: dict[str, dict[str, Any]] = _load_patterns()


class _HtmlSanityChecker(HTMLParser):
    """Minimal html.parser subclass that raises on the first parse error
    and tracks tag balance so a truncated snippet (e.g. `<button aria-la`)
    can be rejected before it reaches downstream consumers.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.open_tags: list[str] = []
        self.void_tags = {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag not in self.void_tags:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        # <br/>-style — nothing to push
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in self.void_tags:
            return
        if not self.open_tags or self.open_tags[-1] != tag:
            raise ValueError(f"unbalanced closing tag </{tag}>")
        self.open_tags.pop()

    def error(self, message: str) -> None:  # noqa: D401 — html.parser override
        raise ValueError(f"HTML parse error: {message}")


def _is_valid_html_fragment(snippet: str) -> bool:
    """Return True if snippet is well-formed enough to be shipped as a fix.

    Empty string, unbalanced tags, or a parse error → False.
    """
    if not isinstance(snippet, str) or not snippet.strip():
        return False
    # Angle-bracket balance: html.parser tolerates truncated tags like
    # `<button type="button" aria-la` at end-of-buffer. Require that every
    # `<` has a matching `>` before the next `<` or end of string.
    depth = 0
    for ch in snippet:
        if ch == "<":
            if depth != 0:
                return False
            depth = 1
        elif ch == ">":
            if depth != 1:
                return False
            depth = 0
    if depth != 0:
        return False
    checker = _HtmlSanityChecker()
    try:
        checker.feed(snippet)
        checker.close()
    except (ValueError, AssertionError):
        return False
    return len(checker.open_tags) == 0


def _strip_code_fences(text: str) -> str:
    """Strip a leading/trailing ```json / ```html / ``` fence pair, if any."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove the opening fence line and the closing fence.
        stripped = _FENCE_RE.sub("", stripped).strip()
    return stripped


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """Parse `text` as JSON, tolerating code fences and leading prose.

    Returns None if no JSON object can be recovered. Callers use None as
    the signal to retry once, then fall back to manual review.
    """
    candidate = _strip_code_fences(text)
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        # Try to grab the first {...} block — models sometimes prefix a sentence.
        m = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _pattern_for(rule_id: str) -> Optional[dict[str, Any]]:
    return _PATTERNS.get(rule_id)


def _build_prompt(violation: dict[str, Any], pattern: Optional[dict[str, Any]]) -> str:
    rule_id = violation.get("ruleId", "unknown")
    snippet = str(violation.get("domSnippet", "")).strip()[:_MAX_SNIPPET_CHARS]
    help_text = str(violation.get("help", "")).strip()
    wcag = ", ".join(violation.get("wcagRef") or [])

    pattern_block: str
    if pattern:
        skeletons = "\n".join(pattern.get("skeleton_examples", []))
        pattern_block = (
            f"Relevant APG pattern: {pattern['apg_pattern']}\n"
            f"WCAG reference:       {pattern.get('wcag_ref', '(see rule)')}\n"
            f"Guidance:             {pattern['guidance']}\n"
            f"Canonical examples:\n{skeletons}"
        )
    else:
        pattern_block = (
            "No APG pattern table entry for this rule. Apply general WCAG "
            "knowledge and STATE in your explanation that this fix is not "
            "grounded in a matched APG pattern so reviewers can treat it "
            "as lower-confidence."
        )

    return (
        "You are patching a real HTML snippet to fix a single accessibility "
        "violation. Output STRICT JSON with exactly two keys: \"fixed_snippet\" "
        "(the corrected HTML) and \"explanation\" (one plain-English sentence "
        "citing the WCAG or ARIA reference). No markdown, no code fences, no "
        "extra keys, no prose outside the JSON.\n\n"
        "Rules:\n"
        "  * Make the SMALLEST change that resolves the cited violation.\n"
        "  * Do NOT invent ARIA attributes or roles — use only real ones.\n"
        "  * Do NOT refactor unrelated markup.\n"
        "  * Do NOT wrap the JSON in ```json fences.\n"
        "  * Return the smallest self-contained HTML fragment that includes "
        "the fix.\n\n"
        f"Violation rule ID: {rule_id}\n"
        f"WCAG tags:         {wcag or '(none provided)'}\n"
        f"Axe help text:     {help_text or '(none)'}\n"
        f"{pattern_block}\n\n"
        f"Original snippet:\n{snippet}\n\n"
        "Return only the JSON object."
    )


def _manual_review(
    original: str,
    explanation: str,
    *,
    error_kind: Optional[str] = None,
    grounded: bool = False,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "aria",
        "original": original,
        "fixed": None,
        "explanation": explanation,
        "confidence": 0.0,
        "needs_manual_review": True,
        "grounded_in_apg": grounded,
    }
    if error_kind:
        entry["error_kind"] = error_kind
    return entry


def _call_model_once(prompt: str) -> str:
    return ai_provider.generate_text(prompt)


def _parse_model_output(
    raw: str, original: str, grounded: bool,
) -> Optional[dict[str, Any]]:
    """Turn a model response into an ai_fix dict.

    Returns None if the response is unusable (missing keys, malformed
    JSON, or HTML sanity check fails), so the caller can retry once
    and then downgrade to manual review.
    """
    obj = _extract_json_object(raw)
    if not obj:
        return None
    fixed = obj.get("fixed_snippet")
    explanation = obj.get("explanation")
    if not isinstance(fixed, str) or not isinstance(explanation, str):
        return None
    fixed = fixed.strip()
    explanation = explanation.strip()
    if not fixed or not explanation:
        return None
    if not _is_valid_html_fragment(fixed):
        return None
    return {
        "type": "aria",
        "original": original,
        "fixed": fixed,
        "explanation": explanation,
        "confidence": 0.7 if grounded else 0.4,
        "needs_manual_review": False,
        "grounded_in_apg": grounded,
    }


def generate_aria_fix(violation: dict[str, Any]) -> dict[str, Any]:
    """Produce an ai_fix dict for one ARIA / semantic violation.

    Every failure path — no APG match, provider error, malformed JSON,
    broken HTML — downgrades to a structured manual-review object.
    """
    rule_id = str(violation.get("ruleId", ""))
    original_snippet = str(violation.get("domSnippet", "")).strip()
    pattern = _pattern_for(rule_id)
    grounded = pattern is not None

    prompt = _build_prompt(violation, pattern)

    for attempt in (1, 2):
        try:
            raw = _call_model_once(prompt)
        except AIProviderError as exc:
            log.warning("aria_fix: provider %s error on attempt %s: %s", exc.kind, attempt, exc)
            return _manual_review(
                original_snippet,
                f"AI provider {exc.kind}: {exc}. Free-tier keys hit rate/quota "
                "limits during normal use — switch AI_PROVIDER or wait for the "
                "quota window and re-run.",
                error_kind=exc.kind,
                grounded=grounded,
            )
        except Exception as exc:  # noqa: BLE001 — pipeline never crashes
            log.exception("aria_fix: unexpected provider error on attempt %s", attempt)
            return _manual_review(
                original_snippet,
                f"Unexpected provider error: {exc}",
                error_kind="upstream",
                grounded=grounded,
            )

        parsed = _parse_model_output(raw, original_snippet, grounded)
        if parsed is not None:
            if not grounded:
                parsed["explanation"] = (
                    parsed["explanation"]
                    + " (Note: no APG pattern-table entry for this rule; "
                    "reviewer should treat this fix as lower-confidence.)"
                )
            return parsed

        log.warning(
            "aria_fix: attempt %s produced unusable output for rule %s",
            attempt, rule_id,
        )

    return _manual_review(
        original_snippet,
        "Model output was malformed or produced broken HTML on both attempts; "
        "needs manual review.",
        error_kind="parse",
        grounded=grounded,
    )
