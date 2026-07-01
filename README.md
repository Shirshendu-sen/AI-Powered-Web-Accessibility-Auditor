# AI-Powered Web Accessibility Auditor

> Paste a URL. Get a WCAG audit and concrete before/after fixes — deterministic for contrast, AI-generated for alt-text and ARIA, with a manual-review path when the model can't be trusted.

<p align="left">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.138-009688?logo=fastapi&logoColor=white" />
  <img alt="Playwright" src="https://img.shields.io/badge/Playwright-1.61-45ba4b?logo=playwright&logoColor=white" />
  <img alt="axe-core" src="https://img.shields.io/badge/axe--core-4.12-663399" />
  <img alt="MongoDB Atlas" src="https://img.shields.io/badge/MongoDB-Atlas-13aa52?logo=mongodb&logoColor=white" />
  <img alt="Gemini" src="https://img.shields.io/badge/Gemini-Flash-4285F4?logo=google&logoColor=white" />
  <img alt="WCAG" src="https://img.shields.io/badge/WCAG-2.1%20AA-1a73e8" />
  <img alt="Status" src="https://img.shields.io/badge/status-in%20development-orange" />
</p>

---

## Table of contents

- [What it does](#what-it-does)
- [Screens](#screens)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Environment variables](#environment-variables)
- [Running the tests](#running-the-tests)
- [Fix strategies](#fix-strategies)
- [Scoring](#scoring)
- [Roadmap](#roadmap)
- [Documentation](#documentation)

---

## What it does

| Capability | How |
|---|---|
| 🔍 **Scan** a public URL for WCAG 2.1 AA violations | Playwright + `@axe-core/playwright` in a Node microservice |
| 🎨 **Fix contrast** deterministically to a self-verified 4.5:1 / 3:1 target | Pure-Python WCAG luminance + HSL search, no AI call |
| 🖼️ **Generate alt-text** grounded in the actual image + surrounding page context | Vision-capable LLM (Gemini Flash by default, OpenRouter fallback) |
| 🧩 **Fix ARIA / semantic issues** grounded in the W3C APG pattern table | LLM with strict JSON output + HTML sanity check + retry once, then manual review |
| 📊 **Score** the page before and projected-after using locked severity weights | Verified-only semantics — only self-checked fixes reduce the after-score |
| 📁 **Persist** every scan + violation + generated fix | MongoDB Atlas |
| 📤 **Export** the exact on-screen result | Byte-accurate JSON download from the dashboard |

**Non-goals (locked v1 scope):**

- ❌ No authenticated / logged-in page scanning
- ❌ No auto-apply — the tool proposes fixes, it never modifies the target site
- ❌ No full AAA coverage — AA only
- ❌ No fake "fixed ✅" badges — every fix shows the real before/after diff

---

## Screens

> The dashboard is Phase 8 (Next.js + Tailwind). Screenshots go here once benchmarks are logged in Phase 11.

```
┌─────────────────────────────────────────────────────────────┐
│  Accessibility Auditor                                       │
│  Paste a public URL. We'll scan for WCAG violations and     │
│  generate before/after fixes.                                │
│                                                              │
│  ┌───────────────────────────────────────┐  ┌────────────┐  │
│  │ https://example.com                    │  │    Scan    │  │
│  └───────────────────────────────────────┘  └────────────┘  │
│                                                              │
│  ┌── Results ─────────────────────────────  [ Export JSON ] │
│  │                                                            │
│  │  Score before  │  Projected after  │  Improvement │  ✓  │
│  │      33        │        19         │   14 (42%)   │ ok  │
│  │                                                            │
│  │  ▸ Serious (4)                                            │
│  │    ┌─ color-contrast ─────────────── WCAG 1.4.3 ────┐   │
│  │    │ ORIGINAL              │ FIXED                    │  │
│  │    │ <a>needs contrast</a> │ <a>needs contrast</a>    │  │
│  │    │ fg: #ff9999           │ fg: #cf5252              │  │
│  │    │ Adjusted foreground to reach 4.51:1 (target 4.5:1)  │  │
│  │    │ Confidence ▓▓▓▓▓▓▓▓▓▓                              │  │
│  │    └───────────────────────────────────────────────────┘  │
│  │                                                            │
│  │  ▸ Critical (1)                                            │
│  │    ┌─ button-name ── needs manual review (rate_limit) ─┐ │
│  │    │ <button></button>     │ ⚠  This fix needs a human   │  │
│  │    │                       │    reviewer.                 │  │
│  │    └───────────────────────────────────────────────────┘  │
│  └────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
      ┌─────────────────────────────┐
      │  Browser  · Next.js + TW    │  Phase 8
      │  URL input · results · diff │
      └──────────────┬──────────────┘
                     │ POST /api/scans
                     ▼
      ┌─────────────────────────────┐
      │  Backend API · FastAPI      │  Phase 7
      │  URL validation             │
      │  orchestration + scoring    │
      └───┬──────────┬──────────┬───┘
          │          │          │
    HTTP  │    per-  │    Motor │
          ▼    viol. ▼    async ▼
   ┌──────────┐  ┌──────────┐  ┌──────────────┐
   │ Scanner  │  │ Fixers   │  │ MongoDB Atlas│
   │ Node +   │  │ contrast │  │ scans        │
   │ Playw.+  │  │ alt_text │  │ violations   │
   │ axe-core │  │ aria_fix │  │ (users stub) │
   │ Phase 2  │  │ P3 P4 P5 │  │ Phase 1      │
   └──────────┘  └────┬─────┘  └──────────────┘
                      │
                      │ Gemini / OpenRouter
                      ▼
             ┌─────────────────┐
             │  AI provider    │  Phase 4 / 5
             │  (env-selected) │
             └─────────────────┘
```

**Deployment target:** Vercel (frontend) · Render (backend API + scanner as separate services) — Phase 10.

---

## Tech stack

<table>
<tr>
  <th>Layer</th>
  <th>Technology</th>
  <th>Why (per <a href="docs/guide.md#22-locked-stack">Section 2.2 · Locked</a>)</th>
</tr>
<tr>
  <td>Scanner worker</td>
  <td>Node.js + Playwright + <code>@axe-core/playwright</code>, Dockerized</td>
  <td>The industry-standard automation stack; axe-core is the reference implementation for WCAG rules</td>
</tr>
<tr>
  <td>Backend API + fixers</td>
  <td>Python 3.11+ · FastAPI · Motor · Pydantic v2</td>
  <td>Async orchestration + native ergonomics for the AI SDK path</td>
</tr>
<tr>
  <td>Frontend</td>
  <td>Next.js 16 (App Router) + Tailwind CSS 4 · TypeScript</td>
  <td>Fast SSR-first framework with a small, ownable component surface</td>
</tr>
<tr>
  <td>Database</td>
  <td>MongoDB Atlas (free M0)</td>
  <td>Schema flexibility for the <code>ai_fix</code> sub-document; free tier is real, not trial</td>
</tr>
<tr>
  <td>AI provider (default)</td>
  <td>Google Gemini Flash via <code>google-genai</code></td>
  <td>Permanent no-credit-card free tier; one key covers vision (alt-text) + text (ARIA)</td>
</tr>
<tr>
  <td>AI provider (fallback)</td>
  <td>OpenRouter (<code>:free</code> models) via raw <code>httpx</code></td>
  <td>OpenAI-compatible endpoint reachable with existing deps — no extra SDK</td>
</tr>
</table>

---

## Repository layout

```
accessibility-auditor/
├── apps/
│   ├── backend/                 Python FastAPI · fixers · scoring · orchestration
│   │   ├── app/
│   │   │   ├── main.py          FastAPI app · CORS · exception handlers
│   │   │   ├── config.py        env loader
│   │   │   ├── db.py            Motor async singleton
│   │   │   ├── models.py        Pydantic v2 · Section 2.3 schemas
│   │   │   ├── ai_provider.py   Gemini / OpenRouter dispatch
│   │   │   ├── scoring.py       severity-weighted score (locked weights)
│   │   │   ├── routes/scans.py  POST /api/scans · GET /api/scans/{id}
│   │   │   ├── fixers/
│   │   │   │   ├── contrast.py  deterministic WCAG contrast fixer
│   │   │   │   ├── alt_text.py  vision-model alt-text
│   │   │   │   └── aria_fix.py  APG-grounded ARIA fixer
│   │   │   ├── data/aria_patterns.json
│   │   │   └── tests/           pytest gates (per-phase)
│   │   └── requirements.txt
│   └── frontend/                Next.js 16 + Tailwind + TS · App Router
│       └── src/
│           ├── lib/api.ts       typed backend client
│           └── app/
│               ├── page.tsx     URL input → results → JSON export
│               └── components/
│                   ├── ScanForm.tsx
│                   └── ResultsDashboard.tsx  (inlines DiffViewer)
├── services/
│   └── scanner/                 Node + Playwright + axe-core microservice
│       └── src/
│           ├── server.js        Express · /healthz · POST /scan
│           ├── scan.js          runScan · closes context in finally
│           └── severityMap.js   axe → spec-shaped record
├── docs/
│   ├── guide.md                 canonical execution guide (source of truth)
│   └── benchmarks/raw/          Phase 11 archive
├── .env.example                 consolidated env reference (names only)
├── .gitignore
└── README.md
```

---

## Quick start

Prerequisites: **Node ≥ 18**, **Python ≥ 3.11**, **Docker**, **Git**, and a **MongoDB Atlas** M0 cluster.

### 1. Clone and install

```bash
git clone https://github.com/Shirshendu-sen/AI-Powered-Web-Accessibility-Auditor.git
cd AI-Powered-Web-Accessibility-Auditor

# Backend
cd apps/backend
python -m venv venv && source venv/Scripts/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Scanner
cd ../../services/scanner
npm install
npx playwright install chromium

# Frontend
cd ../../apps/frontend
npm install
```

### 2. Configure env

Copy each `.env.example` next to its `.env` and fill in real values (they are gitignored):

```bash
cp apps/backend/.env.example apps/backend/.env
cp apps/frontend/.env.local.example apps/frontend/.env.local
```

See [Environment variables](#environment-variables) below for what each key means.

### 3. Run the three services

Open three terminals from the repo root:

```bash
# Terminal A — scanner (port 4000)
cd services/scanner && PORT=4000 npm start

# Terminal B — backend API (port 8000)
cd apps/backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# Terminal C — frontend (port 3000)
cd apps/frontend && npm run dev
```

Open **http://localhost:3000**, paste a public URL, click **Scan**.

---

## Environment variables

Real values live in each service's local `.env` (never committed). The root `.env.example` and per-service `.env.example` files carry names + non-secret defaults only.

<table>
<tr><th>Variable</th><th>Where</th><th>Required for</th><th>Notes</th></tr>
<tr><td><code>MONGODB_URI</code></td><td>backend</td><td>Phase 1+</td><td>SRV connection string from Atlas → Database → Connect</td></tr>
<tr><td><code>MONGODB_DB_NAME</code></td><td>backend</td><td>Phase 1+</td><td>Default: <code>accessibility_auditor</code></td></tr>
<tr><td><code>AI_PROVIDER</code></td><td>backend</td><td>Phase 4+</td><td>Exactly <code>gemini</code> or <code>openrouter</code> — no silent default</td></tr>
<tr><td><code>GEMINI_API_KEY</code></td><td>backend</td><td>Phase 4–5 (if gemini)</td><td>aistudio.google.com/app/apikey — free tier, no card</td></tr>
<tr><td><code>OPENROUTER_API_KEY</code></td><td>backend</td><td>Phase 4–5 (if openrouter)</td><td>openrouter.ai/keys</td></tr>
<tr><td><code>OPENROUTER_MODEL</code></td><td>backend</td><td>Phase 4–5 (if openrouter)</td><td>A current vision-capable <code>:free</code> slug</td></tr>
<tr><td><code>MAX_IMAGES_PER_SCAN</code></td><td>backend</td><td>Phase 4+</td><td>Cost-control cap (default 5)</td></tr>
<tr><td><code>SCANNER_SERVICE_URL</code></td><td>backend</td><td>Phase 7+</td><td>Default: <code>http://127.0.0.1:4000</code></td></tr>
<tr><td><code>CORS_ALLOWED_ORIGINS</code></td><td>backend</td><td>Phase 7+</td><td>Comma-separated · <b>never</b> use <code>*</code> in prod</td></tr>
<tr><td><code>BACKEND_PORT</code></td><td>backend</td><td>Phase 7+</td><td>Default: <code>8000</code></td></tr>
<tr><td><code>PORT</code></td><td>scanner</td><td>Phase 2+</td><td>Render auto-injects at deploy time</td></tr>
<tr><td><code>NEXT_PUBLIC_API_BASE_URL</code></td><td>frontend</td><td>Phase 8+</td><td>Default: <code>http://127.0.0.1:8000</code></td></tr>
</table>

> ⚠️ **Secrets never enter tracked files.** The `.env.example` files carry names + safe defaults only.

---

## Running the tests

Each phase has a dedicated pytest gate that must pass before the next phase begins.

```bash
cd apps/backend

# Phase 1 — MongoDB (real Atlas roundtrip)
./venv/Scripts/python.exe -m pytest tests/test_db_connection.py -v

# Phase 3 — Contrast fixer (13 tests)
./venv/Scripts/python.exe -m pytest app/fixers/tests/test_contrast.py -v

# Phase 4 — Alt-text fixer (12 unit + 1 integration)
./venv/Scripts/python.exe -m pytest app/fixers/tests/test_alt_text.py -v

# Phase 5 — ARIA fixer (15 unit + 3 integration)
./venv/Scripts/python.exe -m pytest app/fixers/tests/test_aria_fix.py -v

# Phase 6 — Scoring engine (12 tests + real Mongo persistence)
./venv/Scripts/python.exe -m pytest app/tests/test_scoring.py -v

# Phase 7 — API (13 tests · mocked scanner + real Mongo)
./venv/Scripts/python.exe -m pytest app/tests/test_api.py -v
```

Scanner (Phase 2) tests are exercised via `curl` per `docs/guide.md`. Frontend (Phase 8) tests are `npm run build` + a manual click-through — see the guide's Phase 8 phase-level validation.

Integration tests skip gracefully on free-tier quota exhaustion — the fallback IS the spec.

---

## Fix strategies

Each fix returns the same `ai_fix` sub-document. `confidence` is fixed for deterministic fixers; a reduced value flags lower confidence on grounded but non-verified AI fixes.

| Type | Method | Confidence | Fallback |
|---|---|---|---|
| **Contrast** | WCAG relative-luminance + bounded HSL search, self-verified against target + ε | `1.0` (deterministic) | Manual-review if search can't converge without visual extreme |
| **Alt-text** | Fetch image → prompt vision model with surrounding text → ban "image of…" boilerplate | `0.7` on success, `0.9` if decorative | Manual-review on fetch fail, bad content-type, 429, auth, timeout, empty response, or cap reached |
| **ARIA / semantic** | Ground in APG pattern table → strict-JSON prompt → parse defensively → sanity-check HTML → retry once | `0.7` if APG-grounded, `0.4` otherwise | Manual-review on both attempts malformed, or provider error |

Every fix path can degrade to a structured **needs-manual-review** object with an `error_kind`; the pipeline never crashes.

---

## Scoring

Weights are 🔒 locked in [Section 2.5](docs/guide.md#25-severity-weights) — a lower total is better:

<table>
<tr><td>🔴 <code>critical</code></td><td align="right"><b>10</b></td></tr>
<tr><td>🟠 <code>serious</code></td><td align="right"><b>7</b></td></tr>
<tr><td>🟡 <code>moderate</code></td><td align="right"><b>4</b></td></tr>
<tr><td>⚪ <code>minor</code></td><td align="right"><b>2</b></td></tr>
</table>

**`score_after` uses verified-only semantics** — a violation only drops out of the after-score if its fix is (a) contrast-deterministic, or (b) alt-text without a manual-review flag, or (c) ARIA with a passing HTML sanity check. Manual-review fallbacks are counted as still-broken.

**Invariant:** `score_after ≤ score_before`, always. A "fix" that ever increases the score is a bug and the API will fail loudly.

---

## Roadmap

<table>
<tr><td>✅</td><td><b>Phase 0</b></td><td>Repo scaffolding · gitignored env layout</td></tr>
<tr><td>✅</td><td><b>Phase 1</b></td><td>MongoDB Atlas · Motor client · locked schemas + indexes</td></tr>
<tr><td>✅</td><td><b>Phase 2</b></td><td>Scanner microservice · Playwright + axe-core · SSRF-safe URL validation</td></tr>
<tr><td>✅</td><td><b>Phase 3</b></td><td>Deterministic contrast fixer · self-verified</td></tr>
<tr><td>✅</td><td><b>Phase 4</b></td><td>Vision-model alt-text · <code>MAX_IMAGES_PER_SCAN</code> cap · structured fallbacks</td></tr>
<tr><td>✅</td><td><b>Phase 5</b></td><td>APG-grounded ARIA fixer · JSON parse + HTML sanity check + one retry</td></tr>
<tr><td>✅</td><td><b>Phase 6</b></td><td>Scoring engine · verified-only <code>score_after</code></td></tr>
<tr><td>✅</td><td><b>Phase 7</b></td><td>FastAPI orchestration · structured error handler · request logging</td></tr>
<tr><td>✅</td><td><b>Phase 8</b></td><td>Next.js dashboard · real before/after diff · JSON export</td></tr>
<tr><td>⬜</td><td><b>Phase 9</b></td><td>Docker (scanner) via official Playwright base image</td></tr>
<tr><td>⬜</td><td><b>Phase 10</b></td><td>Deploy · Vercel (frontend) + Render (backend + scanner)</td></tr>
<tr><td>⬜</td><td><b>Phase 11</b></td><td>Benchmarks · manual-review accuracy % on N ≥ 5 real sites</td></tr>
<tr><td>⬜</td><td><b>Phase 12</b></td><td>Docs & maintenance protocol · CHANGELOG</td></tr>
</table>

---

## Documentation

- **[`docs/guide.md`](docs/guide.md)** — the phase-by-phase execution guide. **This is the source of truth** for architecture, credentials, decisions, and every ✅ TEST gate. When in doubt, the guide wins.
- **`docs/benchmarks.md`** (Phase 11) — real-site accuracy numbers backed by raw JSON archives in `docs/benchmarks/raw/`.
- **[Section 2 · Architecture Reference](docs/guide.md#2-architecture-reference-)** — 🔒 locked data flow, stack, and schemas.
- **[Appendix A · Env var reference](docs/guide.md#appendix-a--environment-variable-reference)** — every variable, where it's used, when it becomes required.

---

<p align="center">
  <sub>
    Built as a portfolio project by <a href="https://github.com/Shirshendu-sen">Shirshendu Sen</a> · following <a href="docs/guide.md">the guide</a> · phase-gated, evidence-driven.
  </sub>
</p>
