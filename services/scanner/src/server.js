'use strict';

require('dotenv').config();

const express = require('express');
const cors = require('cors');
const net = require('node:net');

const { runScan } = require('./scan');

const PORT = process.env.PORT || 4000;

// In-memory concurrency guard: reject a second /scan while one is in flight
// for this process. Render free-tier RAM is tight; running two Chromium
// contexts at once is the fastest path to OOM.
let scanInProgress = false;

const app = express();
app.use(cors());
app.use(express.json());

app.get('/healthz', (req, res) => {
  res.status(200).json({ status: 'ok' });
});

function isPrivateOrLoopbackIp(host) {
  if (net.isIPv4(host)) {
    const [a, b] = host.split('.').map(Number);
    if (a === 10) return true;
    if (a === 127) return true;
    if (a === 169 && b === 254) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 192 && b === 168) return true;
    if (a === 0) return true;
    return false;
  }
  if (net.isIPv6(host)) {
    const normalized = host.toLowerCase();
    if (normalized === '::1') return true;
    if (normalized.startsWith('fc') || normalized.startsWith('fd')) return true;
    if (normalized.startsWith('fe80')) return true;
    return false;
  }
  return false;
}

function validateTargetUrl(rawUrl) {
  if (typeof rawUrl !== 'string' || rawUrl.length === 0) {
    return { ok: false, error: 'url must be a non-empty string' };
  }
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return { ok: false, error: 'url is not a valid URL' };
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { ok: false, error: 'only http and https URLs are allowed' };
  }
  const host = parsed.hostname.toLowerCase();
  if (
    host === 'localhost' ||
    host.endsWith('.localhost') ||
    host === '0.0.0.0' ||
    isPrivateOrLoopbackIp(host)
  ) {
    return { ok: false, error: 'localhost and private-IP targets are not allowed' };
  }
  return { ok: true, url: parsed.toString() };
}

app.post('/scan', async (req, res) => {
  const validation = validateTargetUrl(req.body && req.body.url);
  if (!validation.ok) {
    return res.status(400).json({ error: validation.error });
  }

  if (scanInProgress) {
    return res.status(429).json({ error: 'scan in progress' });
  }
  scanInProgress = true;

  const memBefore = process.memoryUsage().rss;
  const startedAt = Date.now();
  try {
    const violations = await runScan(validation.url);
    const memAfter = process.memoryUsage().rss;
    return res.status(200).json({
      url: validation.url,
      durationMs: Date.now() - startedAt,
      memory: { before: memBefore, after: memAfter },
      violations,
    });
  } catch (err) {
    console.error('scan failed:', err);
    return res.status(502).json({ error: 'scan failed', detail: String(err && err.message || err) });
  } finally {
    scanInProgress = false;
  }
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`scanner listening on ${PORT}`);
  });
}

module.exports = { app, validateTargetUrl };
