"""Severity-weighted scoring engine (Phase 6).

Weights are locked in Section 2.5 of docs/guide.md — do not change without
recording explicit approval there. The score is a simple weight sum; a
lower total means better accessibility.

`score_after` uses the "verified-only" semantics chosen at build time:
a violation only drops from the after-score if its ai_fix passed its own
internal verification (contrast: not needs_manual_review; alt_text: not
needs_manual_review; aria: not needs_manual_review). This is the credible
variant per the guide's own recommendation.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

log = logging.getLogger(__name__)

# 🔒 Locked — do not change without approval recorded in docs/guide.md.
SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 10,
    "serious": 7,
    "moderate": 4,
    "minor": 2,
}


def _weight_for(severity: Any) -> int:
    """Return the weight for a severity string.

    Unknown severities (e.g. axe's `info` level) return 0 and log a
    warning per the Phase 6 Common Issues table — never crash, never
    silently swallow.
    """
    if isinstance(severity, str) and severity in SEVERITY_WEIGHTS:
        return SEVERITY_WEIGHTS[severity]
    log.warning("scoring: unknown severity %r — treating as weight 0", severity)
    return 0


def compute_score(violations: Iterable[Mapping[str, Any]]) -> int:
    """Sum the severity weights across all violations.

    Same DOM node tripping multiple rules is counted once per violation
    per the guide's Common Issues note — deduplication is out of scope
    without approval.
    """
    total = 0
    for v in violations:
        total += _weight_for(v.get("severity") if isinstance(v, Mapping) else None)
    return total


def _fix_is_verified(ai_fix: Any) -> bool:
    """A fix counts as verified if it exists and did NOT downgrade to
    manual review. Contrast fixer marks its own self-check; alt-text
    and aria fixers set needs_manual_review=True on every failure path.
    """
    if not isinstance(ai_fix, Mapping):
        return False
    if ai_fix.get("needs_manual_review") is True:
        return False
    fixed = ai_fix.get("fixed")
    # Empty-alt for decorative images IS a valid fix — an empty string
    # is intentional there, so we treat presence of the "fixed" key
    # (even as empty string) as sufficient when manual-review is False.
    return fixed is not None


def compute_before_after(
    violations_with_fixes: Iterable[Mapping[str, Any]],
) -> tuple[int, int]:
    """Return (score_before, score_after) using verified-only semantics.

    Each item in `violations_with_fixes` is either:
      * a violation dict that already contains an `ai_fix` sub-dict, or
      * a wrapper like `{"violation": v, "ai_fix": f}` (as produced by
        alt_text.process_alt_text_violations).
    """
    before = 0
    after = 0
    for item in violations_with_fixes:
        if not isinstance(item, Mapping):
            continue
        violation = item.get("violation") if "violation" in item else item
        ai_fix = item.get("ai_fix") if "ai_fix" in item else (
            violation.get("ai_fix") if isinstance(violation, Mapping) else None
        )
        weight = _weight_for(violation.get("severity") if isinstance(violation, Mapping) else None)
        before += weight
        if not _fix_is_verified(ai_fix):
            after += weight

    # Invariant per Phase 6 phase-level validation.
    if after > before:
        raise AssertionError(
            f"scoring invariant violated: score_after={after} > score_before={before}"
        )
    return before, after
