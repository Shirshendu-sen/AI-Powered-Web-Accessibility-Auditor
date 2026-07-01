'use strict';

const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');

const { mapAxeResults, isImageAltRule } = require('./severityMap');

const NAV_TIMEOUT_MS = 20_000;
const CONTEXT_CHARS = 300;

/**
 * For every image-alt violation, resolve the image's absolute src and a
 * short surrounding-text context. Phase 4's alt-text fixer needs both;
 * without this the fixer would fabricate descriptions.
 *
 * Runs one page.evaluate per unique selector list — cheap even on
 * heavily-violating pages.
 */
async function enrichImageAltContext(page, violations) {
  const targets = [];
  for (const v of violations) {
    if (!isImageAltRule(v.ruleId)) continue;
    const selector = Array.isArray(v.target) && v.target.length > 0 ? v.target[0] : null;
    if (!selector) continue;
    targets.push({ selector, ref: v });
  }
  if (targets.length === 0) return;

  const selectors = targets.map((t) => t.selector);
  const contexts = await page.evaluate(
    ({ selectors, contextChars }) => {
      const results = [];
      for (const sel of selectors) {
        let el;
        try {
          el = document.querySelector(sel);
        } catch {
          el = null;
        }
        if (!el) {
          results.push(null);
          continue;
        }
        const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
        const absoluteSrc = src ? new URL(src, document.baseURI).toString() : '';
        const parent = el.closest(
          'figure, article, section, li, p, div, main, header, footer, nav, aside',
        ) || el.parentElement || document.body;
        const raw = (parent.innerText || parent.textContent || '').replace(/\s+/g, ' ').trim();
        const surrounding = raw.slice(0, contextChars);
        const role = el.getAttribute('role') || '';
        const width = el.getAttribute('width') || (el.width || 0);
        const height = el.getAttribute('height') || (el.height || 0);
        results.push({ src: absoluteSrc, surrounding, role, width, height });
      }
      return results;
    },
    { selectors, contextChars: CONTEXT_CHARS },
  );

  targets.forEach(({ ref }, i) => {
    const ctx = contexts[i];
    if (ctx) {
      ref.context = ctx;
    }
  });
}

async function runScan(url) {
  const browser = await chromium.launch({ headless: true });
  let context;
  try {
    context = await browser.newContext();
    const page = await context.newPage();

    await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout: NAV_TIMEOUT_MS,
    });

    const raw = await new AxeBuilder({ page }).analyze();
    const violations = mapAxeResults(raw);
    await enrichImageAltContext(page, violations);
    return violations;
  } finally {
    if (context) {
      await context.close();
    }
    await browser.close();
  }
}

module.exports = { runScan };
