"""Deterministic WCAG contrast fixer.

Implements the WCAG relative-luminance and contrast-ratio formulas directly
(https://www.w3.org/WAI/GL/wiki/Relative_luminance,
https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html) so the
math stays auditable — no opaque colour library standing in for it.

The adjuster nudges the foreground's HSL lightness in bounded steps until
the ratio hits target + epsilon, always re-verifying its own output before
returning it. If it can't get there within the iteration cap, it returns
a "needs manual review" fallback instead of a fabricated pass.
"""

from __future__ import annotations

import colorsys
import re
from typing import Any, Optional

# WCAG 2.1 SC 1.4.3 (AA):
#   - normal text: 4.5:1
#   - large text (>=18pt or >=14pt bold) and UI/graphical objects: 3:1
NORMAL_TEXT_TARGET = 4.5
LARGE_TEXT_TARGET = 3.0

# Small ratio buffer so rounding oscillations don't fail the self-check.
EPSILON = 0.05

MAX_ADJUST_ITERATIONS = 50

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_RGB_RE = re.compile(
    r"^\s*rgba?\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*(?:,\s*(-?\d+(?:\.\d+)?)\s*)?\)\s*$"
)


Rgb = tuple[int, int, int]


def parse_color(value: str, background: Optional[Rgb] = None) -> Optional[Rgb]:
    """Parse `#rgb`, `#rrggbb`, `rgb(...)`, `rgba(...)` → (r,g,b) 0-255.

    `rgba` is flattened against `background` before returning, so the
    contrast maths never sees an alpha channel.
    """
    if not isinstance(value, str):
        return None
    v = value.strip()
    m = _HEX_RE.match(v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = _RGB_RE.match(v)
    if m:
        r, g, b = (int(round(float(m.group(i)))) for i in (1, 2, 3))
        a_raw = m.group(4)
        r, g, b = (max(0, min(255, c)) for c in (r, g, b))
        if a_raw is not None and background is not None:
            a = max(0.0, min(1.0, float(a_raw)))
            br, bg, bb = background
            r = int(round(a * r + (1 - a) * br))
            g = int(round(a * g + (1 - a) * bg))
            b = int(round(a * b + (1 - a) * bb))
        return (r, g, b)
    return None


def _channel(c: int) -> float:
    """sRGB → linear per WCAG relative-luminance definition."""
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: Rgb) -> float:
    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(rgb1: Rgb, rgb2: Rgb) -> float:
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def rgb_to_hex(rgb: Rgb) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _clamp255(x: float) -> int:
    return max(0, min(255, int(round(x))))


def _shift_lightness(rgb: Rgb, delta: float) -> Rgb:
    r, g, b = (c / 255.0 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0.0, min(1.0, l + delta))
    nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
    return (_clamp255(nr * 255), _clamp255(ng * 255), _clamp255(nb * 255))


def resolve_target_ratio(large_text: bool) -> float:
    return LARGE_TEXT_TARGET if large_text else NORMAL_TEXT_TARGET


def adjust_for_contrast(
    fg_rgb: Rgb,
    bg_rgb: Rgb,
    target_ratio: float,
    large_text: bool = False,  # noqa: ARG001 — kept in signature per guide step 2
) -> Optional[Rgb]:
    """Search HSL-lightness space for a foreground colour that meets
    `target_ratio + EPSILON` against `bg_rgb`.

    Tries both darker and lighter directions and returns whichever hits
    the target first with the smallest visual shift. Returns None if
    neither direction converges inside MAX_ADJUST_ITERATIONS.
    """
    goal = target_ratio + EPSILON
    if contrast_ratio(fg_rgb, bg_rgb) >= goal:
        return fg_rgb

    step = 1.0 / MAX_ADJUST_ITERATIONS  # covers the full [0,1] lightness range
    best: Optional[Rgb] = None
    best_iters = MAX_ADJUST_ITERATIONS + 1

    for direction in (-1.0, 1.0):
        for i in range(1, MAX_ADJUST_ITERATIONS + 1):
            candidate = _shift_lightness(fg_rgb, direction * step * i)
            if contrast_ratio(candidate, bg_rgb) >= goal:
                if i < best_iters:
                    best = candidate
                    best_iters = i
                break

    return best


def _extract_thresholds(data: dict[str, Any]) -> tuple[float, bool]:
    """Read axe's contrast payload → (target ratio, large_text bool).

    axe returns `expectedContrastRatio` as a string like "4.5:1"; when
    that's present we trust it, otherwise we derive from font metrics
    per WCAG SC 1.4.3 (>=18pt, or >=14pt bold → large).
    """
    expected = data.get("expectedContrastRatio")
    if isinstance(expected, str) and ":" in expected:
        try:
            target = float(expected.split(":", 1)[0])
            return target, target <= LARGE_TEXT_TARGET + 0.001
        except ValueError:
            pass
    font_size = float(data.get("fontSize") or 0)  # in pt
    font_weight = float(data.get("fontWeight") or 0)
    large = font_size >= 18.0 or (font_size >= 14.0 and font_weight >= 700)
    return (LARGE_TEXT_TARGET if large else NORMAL_TEXT_TARGET, large)


def _manual_review(original: str, explanation: str) -> dict[str, Any]:
    return {
        "type": "contrast",
        "original": original,
        "fixed": None,
        "explanation": explanation,
        "confidence": 1.0,
        "needs_manual_review": True,
    }


def generate_contrast_fix(violation: dict[str, Any]) -> dict[str, Any]:
    """Turn a Phase 2 contrast violation into the ai_fix dict.

    Confidence is a fixed 1.0 — the method is deterministic and self-
    verified. If we can't reach the target, we mark manual review;
    we never fabricate a passing colour.
    """
    data = violation.get("data") or {}
    fg_str = data.get("fgColor")
    bg_str = data.get("bgColor")
    original_repr = f"fg={fg_str}, bg={bg_str}"

    bg_rgb = parse_color(bg_str) if isinstance(bg_str, str) else None
    fg_rgb = parse_color(fg_str, background=bg_rgb) if isinstance(fg_str, str) else None
    if bg_rgb is None or fg_rgb is None:
        return _manual_review(
            original_repr,
            "Contrast fixer could not parse the axe fgColor/bgColor payload — "
            "needs manual review.",
        )

    target_ratio, large_text = _extract_thresholds(data)
    current_ratio = contrast_ratio(fg_rgb, bg_rgb)

    if current_ratio >= target_ratio + EPSILON:
        original_hex = rgb_to_hex(fg_rgb)
        return {
            "type": "contrast",
            "original": original_hex,
            "fixed": original_hex,
            "explanation": (
                f"Foreground {original_hex} on background {rgb_to_hex(bg_rgb)} already "
                f"meets the {target_ratio}:1 target (measured {current_ratio:.2f}:1). "
                "No change required."
            ),
            "confidence": 1.0,
            "needs_manual_review": False,
        }

    adjusted = adjust_for_contrast(fg_rgb, bg_rgb, target_ratio, large_text=large_text)
    if adjusted is None:
        return _manual_review(
            rgb_to_hex(fg_rgb),
            f"Could not reach {target_ratio}:1 against {rgb_to_hex(bg_rgb)} within "
            f"{MAX_ADJUST_ITERATIONS} bounded HSL steps — the pair is at a visual "
            "extreme where a redesign is needed rather than a colour nudge.",
        )

    # Self-verify before returning — never trust the search loop alone.
    achieved = contrast_ratio(adjusted, bg_rgb)
    if achieved < target_ratio:
        return _manual_review(
            rgb_to_hex(fg_rgb),
            f"Self-verification failed: candidate {rgb_to_hex(adjusted)} measured "
            f"{achieved:.2f}:1 against {rgb_to_hex(bg_rgb)}, below the "
            f"{target_ratio}:1 target.",
        )

    fixed_hex = rgb_to_hex(adjusted)
    original_hex = rgb_to_hex(fg_rgb)
    return {
        "type": "contrast",
        "original": original_hex,
        "fixed": fixed_hex,
        "explanation": (
            f"Adjusted foreground from {original_hex} to {fixed_hex} to reach "
            f"{achieved:.2f}:1 against background {rgb_to_hex(bg_rgb)} "
            f"(target {target_ratio}:1{', large text' if large_text else ''})."
        ),
        "confidence": 1.0,
        "needs_manual_review": False,
    }
