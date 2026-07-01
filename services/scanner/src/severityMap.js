'use strict';

/**
 * Mapping helpers for the raw axe-core result shape into the scanner's
 * public contract:
 *   { ruleId, severity, wcagRef, domSnippet, target, data?, context? }
 *
 * axe `impact` values already match Section 2.5's four severities exactly,
 * so we pass them straight through and default to "minor" when a rule
 * omits impact (rare, but real).
 *
 * `data` is preserved verbatim for downstream fixers that need axe's
 * structured payload (Phase 3 contrast fixer reads fg/bg/thresholds).
 * `context` is populated by scan.js for image-alt violations (Phase 4)
 * before serialization; severityMap does not compute it.
 */

const SEVERITIES = new Set(['critical', 'serious', 'moderate', 'minor']);
const WCAG_TAG_PATTERN = /^wcag\d/i;
const CONTRAST_RULES = new Set(['color-contrast', 'color-contrast-enhanced']);
const IMAGE_ALT_RULES = new Set([
  'image-alt',
  'input-image-alt',
  'role-img-alt',
  'svg-img-alt',
  'area-alt',
]);

function mapSeverity(rawImpact) {
  if (rawImpact && SEVERITIES.has(rawImpact)) return rawImpact;
  return 'minor';
}

function extractWcagRefs(tags) {
  if (!Array.isArray(tags)) return [];
  return tags.filter((t) => typeof t === 'string' && WCAG_TAG_PATTERN.test(t));
}

function isContrastRule(ruleId) {
  return CONTRAST_RULES.has(ruleId);
}

function isImageAltRule(ruleId) {
  return IMAGE_ALT_RULES.has(ruleId);
}

/**
 * Extract the first non-empty `data` payload found across a node's
 * `any` / `all` / `none` checkResult arrays. axe attaches contrast
 * data (fgColor, bgColor, contrastRatio, expectedContrastRatio,
 * fontSize, fontWeight) to whichever check actually fired.
 */
function extractCheckData(node) {
  for (const bucket of ['any', 'all', 'none']) {
    const checks = Array.isArray(node[bucket]) ? node[bucket] : [];
    for (const c of checks) {
      if (c && c.data && typeof c.data === 'object') {
        return c.data;
      }
    }
  }
  return null;
}

function mapAxeViolation(rawViolation) {
  const severity = mapSeverity(rawViolation.impact);
  const wcagRef = extractWcagRefs(rawViolation.tags);
  const ruleId = rawViolation.id;
  const description = typeof rawViolation.description === 'string' ? rawViolation.description : '';
  const help = typeof rawViolation.help === 'string' ? rawViolation.help : '';
  const nodes = Array.isArray(rawViolation.nodes) ? rawViolation.nodes : [];

  const base = { ruleId, severity, wcagRef, description, help };

  if (nodes.length === 0) {
    return [{ ...base, domSnippet: '', target: [] }];
  }

  return nodes.map((node) => {
    const record = {
      ...base,
      domSnippet: typeof node.html === 'string' ? node.html : '',
      target: Array.isArray(node.target) ? node.target : [],
    };
    const data = extractCheckData(node);
    if (data !== null) {
      record.data = data;
    }
    return record;
  });
}

function mapAxeResults(raw) {
  const violations = Array.isArray(raw && raw.violations) ? raw.violations : [];
  return violations.flatMap(mapAxeViolation);
}

module.exports = {
  mapSeverity,
  extractWcagRefs,
  extractCheckData,
  isContrastRule,
  isImageAltRule,
  mapAxeViolation,
  mapAxeResults,
};
