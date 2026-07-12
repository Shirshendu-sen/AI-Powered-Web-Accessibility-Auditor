<div align="center">

# ♿ AI-Powered Web Accessibility Auditor

**Paste a URL. Get a WCAG 2.1 AA audit with concrete before/after fixes — deterministic for contrast, AI-generated for alt-text and ARIA, with a manual-review path when the model can't be trusted.**

[![Next.js 16](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.138-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Playwright](https://img.shields.io/badge/Playwright-1.61-45ba4b?logo=playwright&logoColor=white)](https://playwright.dev/)
[![axe-core](https://img.shields.io/badge/axe--core-4.12-663399)](https://www.deque.com/axe/)
[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-13aa52?logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Gemini](https://img.shields.io/badge/Gemini-Flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-fallback-FF6B6B?logo=openai&logoColor=white)](https://openrouter.ai/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![WCAG 2.1 AA](https://img.shields.io/badge/WCAG-2.1%20AA-1a73e8)](https://www.w3.org/TR/WCAG21/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>

---

## 📋 Table of Contents

- [What It Does](#-what-it-does)
- [Demo & Screenshots](#-demo--screenshots)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Repository Layout](#-repository-layout)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [Running the Tests](#-running-the-tests)
- [Fix Strategies](#-fix-strategies)
- [Scoring Model](#-scoring-model)
- [Roadmap / Phase Status](#-roadmap--phase-status)
- [Documentation](#-documentation)
- [License](#-license)

---

## 🎯 What It Does

| Capability | How |
|---|---|
| 🔍 **Scan** a public URL for WCAG 2.1 AA violations | Playwright + `@axe-core/playwright` in a Node.js microservice |
| 🎨 **Fix contrast** deterministically to a self-verified 4.5:1 / 3:1 target | Pure-Python WCAG luminance + HSL search — **no AI call required** |
| 🖼️ **Generate alt-text** grounded in the actual image + surrounding page context | Vision-capable LLM (Gemini Flash by default, OpenRouter as fallback) |
| 🧩 **Fix ARIA / semantic issues** grounded in the W3C APG pattern table | LLM with strict JSON output + HTML sanity check + retry-once, then manual review |
| 📊 **Score** the page before and projected-after using locked severity weights | **Verified-only semantics** — only self-checked fixes reduce the after-score |
| 💾 **Persist** every scan, violation, and generated fix | MongoDB Atlas (free M0 tier) |
| 📤 **Export** results as JSON | Byte-accurate download from the dashboard |

### ❌ What This Project Does *Not* Do (Locked v1 Scope)

| Out of Scope | Reason |
|---|---|
| ❌ Authenticated / logged-in page scanning | Adds auth complexity far beyond the core value prop |
| ❌ Auto-apply fixes to the target site | This tool **proposes fixes**, it never modifies the target site directly |
| ❌ Full WCAG AAA coverage | AA only — AAA adds requirements that aren't testable by automation alone |
| ❌ Fake "fixed ✅" badges | Every fix shows the **real before/after diff** — this is the project's stated differentiator |

---

## 🖼️ Demo & Screenshots

```
┌──────────────────────────────────────────────────────────────────┐
│  ♿ Accessibility Auditor                                         │
│  Paste a public URL. We'll scan for WCAG violations and           │
│  generate before/after fixes.                                     │
│                                                                   │
│  ┌──────────────────────────────────────────┐  ┌──────────────┐  │
│  │ https://example.com                       │  │   🔍 Scan   │  │
│  └──────────────────────────────────────────┘  └──────────────┘  │
│                                                                   │
│  ┌── Results ──────────────────────────────────  [📥 Export JSON] │
│  │                                                                 │
│  │  📊 Score Before │  ✅ Projected After │ 📈 Improvement │ ✓    │
│  │       33         │         19          │   14  (42%)    │  ok  │
│  │                                                                 │
│  │  ◉ Serious (4)                                                 │
│  │  ┌─ color-contrast ────────────────── WCAG 1.4.3 ──────────┐  │
│  │  │ 🔴 ORIGINAL                      │ 🟢 FIXED              │  │
│  │  │ <a>needs contrast</a>            │ <a>needs contrast</a> │  │
│  │  │ Foreground: #ff9999               │ Foreground: #cf5252   │  │
│  │  │ Adjusted foreground to reach 4.51:1 (target 4.5:1)        │  │
│  │  │ Confidence ━━━━━━━━━━━━━━━━━━━━  100%                     │  │
│  │  └───────────────────────────────────────────────────────────┘  │
│  │                                                                 │
│  │  ◉ Critical (1)                                                 │
│  │  ┌─ button-name ──── ⚠ needs manual review (rate_limit) ───┐  │
│  │  │ 🔴 ORIGINAL                      │ ⚠ MANUAL REVIEW        │  │
│  │  │ <button></button>                 │ This fix needs a human │  │
│  │  │                                   │ reviewer.              │  │
│  │  │                                   │ Reason: rate_limit     │  │
│  │  └───────────────────────────────────────────────────────────┘  │
│  └─────────────────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────┘
```

> Run the project locally to see the live dashboard — screenshots will be added here once Phase 11 benchmarks are complete.

---

## 🏗️ Architecture

The system is composed of **three independent services** orchestrated by a single FastAPI backend:

```
            ┌──────────────────────────────────────┐
            │   Browser (Next.js 16 + Tailwind)    │
            │   URL Input · Results · Diff · Export │
            └──────────────┬───────────────────────┘
                           │ POST /api/scans { url }
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Backend API (FastAPI)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ URL Validate│  │ Orchestration│  │ Scoring      │            │
│  │ + CORS      │  │ + Logging    │  │ Engine       │            │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                │                  │                    │
│         ▼                ▼                  ▼                    │
│  ┌──────────┐   ┌───────────────┐   ┌──────────────┐            │
│  │ Scanner  │   │   Fixers      │   │ MongoDB      │            │
│  │ Service  │   │ ┌───────────┐ │   │ Atlas        │            │
│  │ (HTTP)   │   │ │ Contrast  │ │   │ ┌──────────┐ │            │
│  └──────────┘   │ │ (no AI)   │ │   │ │ scans    │ │            │
│                 │ ├───────────┤ │   │ ├──────────┤ │            │
│                 │ │ Alt-Text  │ │   │ │violations│ │            │
│                 │ │ (Vision)  │ │   │ └──────────┘ │            │
│                 │ ├───────────┤ │   └──────────────┘            │
│                 │ │ ARIA Fix  │ │                               │
│                 │ │ (Text)    │ │                               │
│                 │ └─────┬─────┘ │                               │
│                 └───────┼───────┘                               │
└─────────────────────────┼───────────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
            ▼                           ▼
    ┌──────────────────┐      ┌──────────────────┐
    │  Gemini Flash    │      │  OpenRouter      │
    │  (default)       │      │  (fallback)      │
    │  Vision + Text   │      │  Vision + Text   │
    │  google-genai    │      │  httpx / REST    │
    └──────────────────┘      └──────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| **Scanner runs as a separate microservice** | Playwright/Chromium dependency is heavy — keeping it isolated avoids bloating the Python backend |
| **Backend calls scanner over HTTP** | Single public contract from the browser's perspective; internal fan-out keeps each box independently deployable |
| **Per-violation error isolation** | One failed AI fix never aborts the entire scan — that violation downgrades to manual review, the rest continue |
| **Verified-only `score_after`** | Only fixes that pass internal verification reduce the after-score — no fabricated "improvement" numbers |
| **Provider-agnostic AI layer** | Switch between Gemini and OpenRouter via a single env var — no code changes, no redeploys |

---

## 🛠️ Tech Stack

| Layer | Technology | Why (Locked per [Section 2.2](docs/guide.md#22-locked-stack)) |
|---|---|---|
| **Scanner Worker** | Node.js + Playwright + `@axe-core/playwright` (Dockerized) | Industry-standard automation stack; axe-core is the reference WCAG implementation |
| **Backend API + Fixers** | Python 3.11+ · FastAPI · Motor · Pydantic v2 | Async orchestration with native ergonomics for the AI SDK path |
| **Frontend** | Next.js 16 (App Router) + Tailwind CSS 4 + TypeScript | Fast SSR-first framework with a small, ownable component surface |
| **Database** | MongoDB Atlas (free M0 cluster) | Schema flexibility for the `ai_fix` sub-document; the free tier is permanent, not a trial |
| **AI Provider (Default)** | Google Gemini Flash (`google-genai` SDK) | Permanent no-credit-card free tier; one key covers both vision (alt-text) and text (ARIA) |
| **AI Provider (Fallback)** | OpenRouter (`:free` models via raw `httpx`) | OpenAI-compatible endpoint reachable with existing dependencies — no extra SDK to install |

---

## 📁 Repository Layout

```
accessibility-auditor/
├── apps/
│   ├── backend/                          # Python FastAPI: fixers, scoring, orchestration
│   │   ├── app/
│   │   │   ├── main.py                   # FastAPI entrypoint · CORS · exception handlers
│   │   │   ├── config.py                 # Environment loader
│   │   │   ├── db.py                     # Motor async MongoDB singleton
│   │   │   ├── models.py                 # Pydantic v2 schemas (Section 2.3 locked)
│   │   │   ├── ai_provider.py            # Gemini / OpenRouter dispatch (Phase 4+)
│   │   │   ├── scoring.py                # Severity-weighted score engine (Phase 6)
│   │   │   ├── routes/
│   │   │   │   └── scans.py              # POST /api/scans · GET /api/scans/{id}
│   │   │   ├── fixers/
│   │   │   │   ├── contrast.py           # Deterministic WCAG contrast fixer (Phase 3)
│   │   │   │   ├── alt_text.py           # Vision-model alt-text generator (Phase 4)
│   │   │   │   └── aria_fix.py           # APG-grounded ARIA fixer (Phase 5)
│   │   │   ├── data/aria_patterns.json   # W3C APG pattern reference table
│   │   │   └── tests/                    # Pytest gates (per-phase)
│   │   ├── scripts/                       # Utility scripts (index creation, DB check)
│   │   └── requirements.txt
│   └── frontend/                          # Next.js 16 + Tailwind + TypeScript
│       └── src/
│           ├── lib/
│           │   └── api.ts                # Typed backend client
│           └── app/
│               ├── page.tsx              # Main page: URL input → results → export
│               └── components/
│                   ├── ScanForm.tsx       # URL input with validation
│                   ├── ResultsDashboard.tsx  # Score cards + grouped violations
│                   └── DiffViewer.tsx     # Before/after diff per violation
├── services/
│   └── scanner/                           # Node.js + Playwright + axe-core microservice
│       ├── Dockerfile                    # Official Playwright base image
│       └── src/
│           ├── server.js                 # Express: /healthz · POST /scan · concurrency guard
│           ├── scan.js                   # runScan(): browser lifecycle + axe-core
│           └── severityMap.js            # axe impact → spec-shaped violation record
├── docs/
│   ├── guide.md                          # Canonical phase-by-phase execution guide (source of truth)
│   └── benchmarks/raw/                   # Phase 11 raw run archives
├── .env.example                          # Consolidated env variable reference (names only)
├── .gitignore
├── docker-compose.yml                    # Optional: local full-stack with Docker
└── README.md                             # This file
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Minimum Version | Check |
|---|---|---|
| Node.js | ≥ 18 | `node -v` |
| Python | ≥ 3.11 | `python --version` |
| Docker | Any recent | `docker --version` |
| Git | Any recent | `git --version` |
| MongoDB Atlas | Free M0 cluster | [sign up](https://www.mongodb.com/atlas) |

### 1. Clone and Install Dependencies

```bash
git clone https://github.com/Shirshendu-sen/AI-Powered-Web-Accessibility-Auditor.git
cd AI-Powered-Web-Accessibility-Auditor

# --- Backend ---
cd apps/backend
python -m venv venv

# Activate the virtual environment:
# Windows (PowerShell): .\venv\Scripts\Activate.ps1
# Windows (CMD):        venv\Scripts\activate
# macOS / Linux:        source venv/bin/activate

pip install -r requirements.txt

# --- Scanner ---
cd ../../services/scanner
npm install
npx playwright install --with-deps chromium

# --- Frontend ---
cd ../../apps/frontend
npm install
```

### 2. Configure Environment Variables

Each service has its own `.env.example` with documented variables. Copy them and fill in real values:

```bash
# Backend
cp apps/backend/.env.example apps/backend/.env
# Frontend (optional if running locally)
cp apps/frontend/.env.local.example apps/frontend/.env.local
```

> ⚠️ **Secrets never enter tracked files.** The `.env` files are gitignored. Never commit real API keys, MongoDB URIs, or tokens.

**Minimum required setup** (see [Environment Variables](#-environment-variables) for details):

| Variable | Where to Set | Get It From |
|---|---|---|
| `MONGODB_URI` | `apps/backend/.env` | MongoDB Atlas → Database → Connect |
| `AI_PROVIDER` | `apps/backend/.env` | Set to `gemini` or `openrouter` |
| `GEMINI_API_KEY` | `apps/backend/.env` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) (free tier, no credit card) |

### 3. Start All Three Services

Open **three terminal windows** from the repo root:

```bash
# Terminal 1 — Scanner (port 4000)
cd services/scanner
npm start

# Terminal 2 — Backend API (port 8000)
cd apps/backend
# Windows: .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
python -m uvicorn app.main:app --port 8000

# Terminal 3 — Frontend (port 3000)
cd apps/frontend
npm run dev
```

### 4. Run Your First Scan

Open **[http://localhost:3000](http://localhost:3000)** in your browser:

1. Paste a public URL (e.g., `https://example.com`)
2. Click **Scan**
3. View violations grouped by severity with before/after diffs
4. Click **Export JSON** to download the raw result

### Alternative: Docker Compose

```bash
docker-compose up -d
curl http://localhost:4000/healthz   # Scanner health check
```

---

## 🔐 Environment Variables

Real values live in each service's local `.env` (never committed). The root `.env.example` and per-service `.env.example` files carry **names + non-secret defaults only**.

### Backend (`apps/backend/.env`)

| Variable | Required For | Default | Notes |
|---|---|---|---|
| `MONGODB_URI` | Phase 1+ | — | SRV connection string from Atlas Dashboard |
| `MONGODB_DB_NAME` | Phase 1+ | `accessibility_auditor` | Database name in Atlas |
| `AI_PROVIDER` | Phase 4+ | — | Must be exactly `gemini` or `openrouter` |
| `GEMINI_API_KEY` | Phase 4–5 (if `gemini`) | — | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `OPENROUTER_API_KEY` | Phase 4–5 (if `openrouter`) | — | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | Phase 4–5 (if `openrouter`) | — | A current vision-capable `:free` slug |
| `MAX_IMAGES_PER_SCAN` | Phase 4+ | `5` | Cost-control cap |
| `SCANNER_SERVICE_URL` | Phase 7+ | `http://127.0.0.1:4000` | Scanner's local or deployed URL |
| `CORS_ALLOWED_ORIGINS` | Phase 7+ | `http://localhost:3000` | Comma-separated — **never `*` in production** |
| `BACKEND_PORT` | Phase 7+ | `8000` | |

### Scanner (`services/scanner/.env`)

| Variable | Required For | Default | Notes |
|---|---|---|---|
| `PORT` | Phase 2+ | `4000` | Render auto-injects at deploy time |

### Frontend (`apps/frontend/.env.local`)

| Variable | Required For | Default | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Phase 8+ | `http://127.0.0.1:8000` | Points at the backend API |

---

## 🧪 Running the Tests

Each phase has a dedicated pytest gate that must pass before the next phase begins.

### All Backend Tests (One Command)

```bash
cd apps/backend

# Activate venv first:
# Windows: .\venv\Scripts\Activate.ps1
# macOS/Linux: source venv/bin/activate

python -m pytest -v
```

### Individual Test Suites

```bash
cd apps/backend

# Phase 1 — MongoDB Connection & Schema (6 tests)
python -m pytest tests/test_db_connection.py -v

# Phase 3 — Contrast Fixer (13 tests)
python -m pytest app/fixers/tests/test_contrast.py -v

# Phase 4 — Alt-Text Generator (12 unit + 1 integration)
python -m pytest app/fixers/tests/test_alt_text.py -v

# Phase 5 — ARIA Fixer (15 unit + 3 integration)
python -m pytest app/fixers/tests/test_aria_fix.py -v

# Phase 6 — Scoring Engine (12 tests + real MongoDB persistence)
python -m pytest app/tests/test_scoring.py -v

# Phase 7 — Full API (13 tests with mocked scanner + real MongoDB)
python -m pytest app/tests/test_api.py -v
```

### Test Results Summary

| Test Suite | Tests | Status |
|---|---|---|
| MongoDB Connection | 6 | ✅ All Pass |
| Full API | 13 | ✅ All Pass |
| Contrast Fixer | 13 | ✅ All Pass |
| Alt-Text Fixer | 13 | ✅ 12 Pass, 1 Skipped* |
| ARIA Fixer | 18 | ✅ 15 Pass, 3 Skipped* |
| Scoring Engine | 12 | ✅ All Pass |

> *Integration tests that require a real AI provider API call are skipped when the free-tier quota is exhausted. This is **expected behavior** — the fallback path (manual review) is the spec, not a bug. Switch the `AI_PROVIDER` env var or wait for quota reset to run them.

### Scanner Tests

The scanner is tested via `curl` on real public URLs:

```bash
# Health check
curl http://localhost:4000/healthz
# → {"status":"ok"}

# Real scan
curl -X POST http://localhost:4000/scan \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

### Frontend Checks

```bash
cd apps/frontend
npm run lint      # ESLint — no warnings
npm run build     # Production build — must succeed
```

---

## 🧩 Fix Strategies

Every fix returns the same `ai_fix` sub-document. `confidence` is fixed for deterministic fixers; a reduced value flags lower confidence on grounded but non-verified AI fixes.

| Type | Method | Confidence | Manual Review Trigger |
|---|---|---|---|
| **Contrast** | WCAG relative-luminance formula + bounded HSL lightness search, self-verified against `target + ε` | `1.0` (deterministic) | Search can't converge without a visual extreme |
| **Alt-Text** | Fetch image → prompt vision model with surrounding text → strip "image of…" boilerplate | `0.7` on success<br>`0.9` if decorative | Fetch failure, bad content-type, 429 rate limit, auth failure, timeout, empty response, or cap reached |
| **ARIA / Semantic** | Ground in W3C APG pattern table → strict-JSON prompt → defensive parse → HTML sanity check → retry once | `0.7` if APG-grounded<br>`0.4` otherwise | Both attempts produce malformed output, or provider error |

**Every fix path** can degrade to a structured **needs-manual-review** object with an `error_kind` field — the pipeline **never crashes**.

---

## 📊 Scoring Model

Weights are 🔒 locked in [Section 2.5](docs/guide.md#25-severity-weights) of the execution guide. **A lower total score is better.**

| Severity | Weight |
|---|---|
| 🔴 `critical` | **10** |
| 🟠 `serious` | **7** |
| 🟡 `moderate` | **4** |
| ⚪ `minor` | **2** |

### Verified-Only Semantics

`score_after` uses **verified-only semantics** — a violation only drops out of the after-score if its fix satisfies one of:

- **Contrast**: Deterministic algorithm completed and self-verified the output
- **Alt-Text**: Not flagged as manual review (image fetched, provider returned valid text)
- **ARIA**: HTML sanity check passed and JSON parsed correctly

Manual-review fallbacks are counted as **still broken** in the after-score.

**Invariant:** `score_after ≤ score_before` — always. A fix that ever increases the score is a bug and the API will fail loudly.

---

## 🗺️ Roadmap / Phase Status

| Status | Phase | Description |
|---|---|---|
| ✅ Complete | **Phase 0** | Repository scaffolding · gitignored env layout |
| ✅ Complete | **Phase 1** | MongoDB Atlas · async Motor client · locked schemas + indexes |
| ✅ Complete | **Phase 2** | Scanner microservice · Playwright + axe-core · SSRF-safe URL validation |
| ✅ Complete | **Phase 3** | Deterministic contrast fixer · self-verified output |
| ✅ Complete | **Phase 4** | Vision-model alt-text generation · `MAX_IMAGES_PER_SCAN` cap · structured fallbacks |
| ✅ Complete | **Phase 5** | APG-grounded ARIA fixer · JSON parsing + HTML sanity check + retry logic |
| ✅ Complete | **Phase 6** | Scoring engine · verified-only `score_after` semantics |
| ✅ Complete | **Phase 7** | FastAPI orchestration · CORS · structured error handler · request logging |
| ✅ Complete | **Phase 8** | Next.js dashboard · URL input · grouped results · before/after diff · JSON export |
| ⬜ Pending | **Phase 9** | Docker containerization (scanner via official Playwright base image) |
| ⬜ Pending | **Phase 10** | Deployment (Vercel frontend + Render backend + Render scanner) |
| ⬜ Pending | **Phase 11** | Benchmarking & success metrics on N ≥ 5 real sites |
| ⬜ Pending | **Phase 12** | Documentation & maintenance protocol · CHANGELOG |

**8 of 12 phases complete** — the core scanning, fixing, and dashboard functionality is fully operational.

---

## 📚 Documentation

| Document | Description |
|---|---|
| **[`docs/guide.md`](docs/guide.md)** | 📖 **Canonical phase-by-phase execution guide** — the source of truth for architecture, credentials, locked decisions, and every ✅ TEST gate. When in doubt, the guide wins. |
| **[Section 2 · Architecture Reference](docs/guide.md#2-architecture-reference-)** | 🔒 Locked data flow, locked stack (no technology substitutions), collection schemas, out-of-scope boundaries, and severity weights |
| **[Appendix A · Env Var Reference](docs/guide.md#appendix-a--environment-variable-reference)** | Every environment variable across all 12 phases — where it's used, when it becomes required |
| **[Appendix B · Cross-Phase Issues](docs/guide.md#appendix-b--common-cross-phase-issues)** | Known pitfalls: CORS misconfiguration, MongoDB connection drops, AI cost runaway, secret leakage |
| **[Appendix C · Definition of Done](docs/guide.md#appendix-c--definition-of-done-whole-project)** | The complete project-level acceptance criteria |

---

## 📄 License

This project is built as a portfolio project and is available under the [MIT License](LICENSE).

---

<div align="center">
  <sub>
    Built by <a href="https://github.com/Shirshendu-sen">Shirshendu Sen</a> ·
    Following the <a href="docs/guide.md">phase-gated execution guide</a> ·
    Evidence-driven, not demo-driven.
  </sub>
</div>
