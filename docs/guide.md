# Accessibility Auditor & Auto-Fixer — Agent Execution Guide

**Status:** Source of truth for build execution
**Audience:** Autonomous coding agents (primary) and human contributors (secondary)
**Project:** AI-Powered Web Accessibility Auditor & Auto-Fixer

---

## 0. How to Use This Document

This guide replaces the original project description as the operating manual for building this project. It is not a tutorial — it does not explain *why* WCAG matters or *how* axe-core works conceptually. It tells an executing agent exactly what to build, in what order, with what to stop and ask for, and how to prove each step actually works before moving on.

**Legend used throughout:**
- 🛑 **STOP** — the agent must pause and get something from the user (a credential, a decision, an approval) before continuing. The agent must never invent a substitute and continue.
- ✅ **TEST** — a concrete, runnable check that must pass before the next step begins. "It compiles" is not a pass condition unless the step says so explicitly — these are functional checks.
- 🔒 **LOCKED** — content (architecture, schema, weights, scope) that must not be changed without explicit user approval, recorded in this document when changed.

If at any point reality diverges from this guide (a step doesn't work as written, a dependency is wrong, a design decision needs revisiting), the agent fixes the guide itself as part of fixing the code — see Phase 12. A stale guide is a project defect, not a documentation nice-to-have.

---

## 1. AI Agent Rules (Non-Negotiable)

These rules govern every phase below. They are not suggestions.

1. **Follow phases sequentially.** Do not start Phase *N+1* work while Phase *N*'s completion checklist has unchecked items.
2. **Never skip steps, and never change the architecture** in Section 2 (services, data flow, collections, the no-auto-apply rule) without explicit user approval recorded in this document.
3. **Never replace technologies** listed in the 🔒 Locked Stack (Section 2.2) with substitutes (e.g., Puppeteer instead of Playwright, Postgres instead of MongoDB, a different frontend framework) without explicit user approval.
4. **Stop and ask for any required credential** before continuing past that point — API keys, the MongoDB URI, OAuth secrets, hosting tokens, anything listed in Section 3 or flagged 🛑 inline. Continuing past a missing credential by using a placeholder, a mock, or a "we'll fill this in later" stub in a way that lets the step silently "pass" is a rule violation.
5. **Never invent secrets, environment variables, or external resources.** Every env var used in code must appear in `.env.example` with an empty/placeholder value and be explained in Appendix A. The agent never writes a real key, token, or connection string into any file that gets committed.
6. **Test every step immediately after completing it.** Do not write step N+1's code until step N's ✅ TEST has actually been run and has actually passed. If a test fails, fix the step — do not proceed and "come back to it."
7. **Validate every phase before moving to the next** using that phase's Phase-Level Validation & Testing section, in addition to the per-step tests.
8. **Update documentation when changes are made.** Any deviation from this guide (a renamed file, a changed env var, a different library version, a scope change) gets written back into this guide in the same unit of work — see Phase 12.

---

## 2. Architecture Reference 🔒

This section is preserved from the original project specification. It is the contract the rest of this guide implements — do not redesign it while executing phases.

### 2.1 Data Flow

```
[User enters URL]
        │
        ▼
[Scanner Service — Node.js + Playwright + axe-core]
        │  (runs in Docker, headless Chromium)
        ▼
[Violation List: rule, severity, DOM snippet, WCAG ref]
        │
        ▼
[Fix-Generation Service — Python/FastAPI]
        ├─ Alt-text fixes      → Vision-Language Model
        ├─ Contrast fixes      → deterministic luminance algorithm
        └─ ARIA/semantic fixes → LLM grounded in ARIA APG patterns
        │
        ▼
[Scoring Engine — severity-weighted score, before/after delta]
        │
        ▼
[Dashboard — Next.js + Tailwind, diff viewer, exportable report]
        │
        ▼
[Storage — MongoDB Atlas: scan history, scores, saved reports]
```

**Orchestration note (implementation detail, not a deviation):** the Next.js frontend does not call the scanner directly. It calls a single FastAPI backend endpoint, which internally calls the scanner over HTTP, runs fix-generation, computes scores, and persists to MongoDB, then returns the assembled result. This keeps the public contract to one call from the browser's perspective while preserving every box in the diagram above.

### 2.2 Locked Stack

| Layer | Technology | Do not substitute |
|---|---|---|
| Scanner worker | Node.js + Playwright + `@axe-core/playwright`, Dockerized | Puppeteer, Cypress, Selenium |
| Fix-generation + orchestration API | Python + FastAPI | Flask, Django, Express-for-this-layer |
| Frontend | Next.js + Tailwind CSS | Remix, plain React+Vite, Bootstrap |
| Database | MongoDB Atlas (free M0 tier) | Postgres, MySQL, Firebase |
| Deploy targets | Vercel (frontend) · Render (backend API + scanner worker, separate services) | Netlify, Heroku, AWS-from-scratch |

### 2.3 MongoDB Collections 🔒

```text
scans
  { _id, url, scanned_at, score_before, score_after, status }

violations
  { _id, scan_id, rule_id, severity, wcag_ref, dom_snippet,
    ai_fix: { type, original, fixed, explanation, confidence } }

users  (only if optional accounts are added later — not in v1 scope)
  { _id, email, password_hash, created_at }
```

`violations` stays a separate collection referencing `scan_id` — never embed the full violation list inside the `scans` document.

### 2.4 Out of Scope (v1) 🔒

The agent must not build any of the following without a new, explicit user request that supersedes this guide:

- Authenticated/logged-in page scanning
- Full WCAG AAA coverage (AA only)
- Mobile native app accessibility
- Auto-merge / direct site modification — this tool proposes fixes, it never deploys them
- Faking automation of checks that require human judgment (e.g., meaningful reading order) — these are flagged "needs manual review," never guessed

### 2.5 Severity Weights 🔒

```text
critical = 10
serious  = 7
moderate = 4
minor    = 2
(lower total score is better)
```

---

## 3. AI Provider Configuration & Required Credentials

### 3.1 AI Provider Configuration

This project uses one provider-agnostic AI layer, shared by Phase 4 (Alt-Text) and Phase 5 (ARIA/Semantic Fixer). A single environment variable picks the active provider — switching it is a config change, never a code change in either fixer.

| Role | Provider | Tier used in this guide | Why |
|---|---|---|---|
| **Primary** | Google Gemini API | Google AI Studio free tier | Permanent, no-credit-card free tier; current Flash-class Gemini models are natively multimodal, so one key covers Phase 4's vision task and Phase 5's text task |
| **Fallback** | OpenRouter | Free models (`:free`-suffixed model slugs) | Used if Gemini's free quota is exhausted, errors out, or the user prefers it; gives access to several vision-capable open models behind one API |
| Optional future alternative | Anthropic Claude / OpenAI | Paid | Not required by any phase in this guide. Could be added later as a third branch in the resolver below if the project ever needs higher-quality paid fixes — not part of the standard build |

The build and every test in Phases 4 and 5 must pass using only the free tiers of Gemini and OpenRouter. No phase in this guide requires an Anthropic or OpenAI key.

**Provider selection logic** — implemented once, in `apps/backend/app/ai_provider.py`, and imported by both `alt_text.py` (Phase 4) and `aria_fix.py` (Phase 5). Neither fixer imports a provider SDK directly:

```
if AI_PROVIDER == "gemini":
    use Gemini       (GEMINI_API_KEY)
else if AI_PROVIDER == "openrouter":
    use OpenRouter   (OPENROUTER_API_KEY, OPENROUTER_MODEL)
else:
    raise a configuration error — never silently default to a provider
```

**Free-tier mechanics the agent must account for in code, not just in setup docs:**
- **Gemini** — get the key at `aistudio.google.com/app/apikey`, no credit card required. Use the `google-genai` SDK (`from google import genai`), the current officially supported client; the older `google-generativeai` package is deprecated and must not be installed. The client reads `GEMINI_API_KEY` from the environment automatically — no extra wiring needed. The free tier currently covers Flash-class models only (Pro-series models are paid-only as of this writing) and is rate/quota-limited rather than time-limited. Confirm the current free Flash model name in AI Studio's model picker before hardcoding it — treat it as a model *class*, the same way this guide treats "GPT-4-class" elsewhere, since Google periodically retires one Flash generation in favor of the next.
- **OpenRouter** — get the key at `openrouter.ai/keys`, also no credit card required for free models. Its endpoint is OpenAI-compatible in request/response shape, so the fallback path is implemented with the project's existing `httpx` dependency calling `https://openrouter.ai/api/v1/chat/completions` directly — this deliberately avoids adding the `anthropic` or `openai` packages as dependencies just to reach a different vendor. Free model slugs end in `:free`, are rate-limited, and the catalog changes over time; confirm a current vision-capable slug at `openrouter.ai/models` (Price filter: Free) with the user before writing it into `OPENROUTER_MODEL`, rather than assuming a specific name stays available.
- Both free tiers return ordinary rate-limit/quota errors during normal use, not just on misconfiguration. This is exactly the failure mode Phase 4's fallback handling and Phase 5's retry-then-manual-review logic already exist to cover — adding this resolver does not relax either phase's existing error-handling requirements.
- The secret-scanning commands in Phase 0 and Phase 10 check for the `sk-` prefix (OpenRouter/OpenAI/Anthropic-style keys) and Google's `AIzaSy`-prefixed key format. Google has begun migrating some accounts to a different key prefix — confirm the actual prefix of the generated key and extend the scan pattern if it differs, before the first push.

### 3.2 Required Credentials & Accounts — Master Checklist

The agent must work through this list at the point each item is first needed (flagged 🛑 in the relevant phase) — it is reproduced here as a single planning reference so the user can prepare in advance if they want to.

| # | Credential / Account | Needed starting | Where to get it | Env var |
|---|---|---|---|---|
| 1 | MongoDB Atlas connection string | Phase 1 | MongoDB Atlas dashboard → Database → Connect | `MONGODB_URI` |
| 2 | Google AI Studio account + Gemini API key (free tier) — primary AI provider | Phase 4 | aistudio.google.com/app/apikey | `GEMINI_API_KEY` |
| 3 | (Optional) OpenRouter account + API key (free models) — fallback AI provider, also covers Phase 5 | Phase 4 | openrouter.ai/keys | `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` |
| 4 | GitHub repository (push access) | Phase 10 | github.com → New repository | n/a (git remote) |
| 5 | Vercel account linked to the repo | Phase 10 | vercel.com | n/a (dashboard) |
| 6 | Render account, two services (scanner + backend) | Phase 10 | render.com | n/a (dashboard) |

No credential is used before its phase explicitly stops to request it. None are pre-filled, guessed, or mocked into a "looks done" state.

---

## 4. Target Repository Structure

```
accessibility-auditor/
├── apps/
│   ├── frontend/            # Next.js + Tailwind (Phase 8)
│   └── backend/             # Python FastAPI: fixers, scoring, orchestration (Phases 1, 3-7)
├── services/
│   └── scanner/              # Node.js + Playwright + axe-core (Phases 2, 9)
├── docs/
│   ├── guide.md               # this file
│   ├── benchmarks.md          # Phase 11
│   └── benchmarks/raw/        # Phase 11 raw run archives
├── .env.example
├── .gitignore
├── docker-compose.yml         # optional, Phase 9
├── CHANGELOG.md               # Phase 12
└── README.md
```

The agent does not add other top-level directories without recording why in Phase 12's documentation step.

---

## Phase 0 — Repository & Environment Scaffolding

**Goal:** A clean, correctly structured monorepo with baseline tooling, ready for service-specific work to begin. No application logic yet.

**Prerequisites:** Node.js 18+, Python 3.11+, Git, and Docker available in the execution environment.

**🛑 User Action Required:**
- Confirm the Node.js / Python / Docker versions available are acceptable (the agent reports detected versions; if any are missing, the agent stops and asks the user to install them or confirm an alternative environment).
- No accounts or paid credentials are needed for this phase.

**AI Agent Responsibilities:**
- Build exactly the structure in Section 4 — no extra top-level folders, no alternate naming.
- Never commit a real `.env` file at any point, starting now.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Initialize git and confirm toolchain versions.
   ✅ TEST: `node -v`, `python3 --version`, `docker --version`, `git --version` all return sane values; `git status` shows a clean new repo.
2. Create the directory skeleton from Section 4 (`apps/frontend`, `apps/backend`, `services/scanner`, `docs/`, `docs/benchmarks/raw/`).
   ✅ TEST: `find . -maxdepth 3 -type d | sort` output matches the target structure.
3. Create root `.gitignore` covering `node_modules/`, `__pycache__/`, `.env`, `.env.local`, `.next/`, `dist/`, `venv/`, `.venv/`, `*.pyc`.
   ✅ TEST: `git check-ignore -v node_modules .env apps/backend/venv` confirms each path is ignored.
4. Create a root `.env.example` as a **consolidated reference only** — every env var used anywhere in the project, names only, mirroring Appendix A — and a root `README.md` stub pointing at `docs/guide.md` as canonical documentation. Note for later phases: this root file is documentation, not something the running code loads. Each deployable service additionally keeps its **own** local `.env`/`.env.example` colocated with it (`apps/backend/.env.example`, `services/scanner/.env.example`), since each runs from its own working directory, loads its own `.env` via `dotenv`, and deploys to its own Render service. Both layers get updated together whenever a variable is added — never just one.
   ✅ TEST: both files exist and contain no real secret values (`grep -E "sk-|AIzaSy|mongodb\+srv://" .env.example README.md` returns nothing).
5. Copy this guide into `docs/guide.md`.
   ✅ TEST: file exists and renders as valid Markdown.
6. Commit the initial scaffold.
   ✅ TEST: `git log --oneline` shows exactly one commit; `git status` is clean.

**Commands (Quick Reference):**
```bash
git init
mkdir -p apps/frontend apps/backend services/scanner docs/benchmarks/raw
touch .env.example README.md .gitignore
git add -A && git commit -m "chore: scaffold repository structure"
```

**Files to Create/Modify:**
- `.gitignore`, `.env.example`, `README.md`, `docs/guide.md`, empty placeholder dirs above.

**Phase-Level Validation & Testing:**
Review the full tree against Section 4 line by line. Confirm `.env` (not `.env.example`) does not exist anywhere yet, and that if it did, it would be ignored by git.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Wrong Node/Python version active | Use `nvm`/`pyenv` to pin the correct version; record the pinned version in README |
| `.env` accidentally created and staged early | `git rm --cached .env`, confirm `.gitignore` covers it, and if any real value was ever in it, treat it as leaked and ask the user to rotate it |
| CRLF/LF line-ending churn on Windows | Add a `.gitattributes` normalizing to LF before the first real code commit |

**Phase Completion Checklist:**
- [ ] Directory structure matches Section 4 exactly
- [ ] Git initialized with a clean first commit
- [ ] `.env.example` present, `.env` gitignored
- [ ] `docs/guide.md` present and matches this document

---

## Phase 1 — Database Layer (MongoDB Atlas)

**Goal:** A live MongoDB connection the backend can read/write, with the three 🔒 collections and their indexes in place, verified end-to-end before any other service depends on it.

**Prerequisites:** Phase 0 complete.

**🛑 User Action Required (STOP — required before any real connection code runs):**
- Create a MongoDB Atlas account and a free **M0** cluster if one doesn't already exist.
- Create a database user and obtain the connection string (URI).
- Whitelist network access (either the agent's/dev IP, or `0.0.0.0/0` for a portfolio-demo project where that tradeoff is acceptable — confirm which with the user).
- Confirm the database name (default suggestion: `accessibility_auditor`) or supply a different one.
- Provide the resulting `MONGODB_URI` value. The agent must not write or test any real connection logic against a placeholder string — local schema/unit tests may use an in-memory or mocked Mongo, but the real connectivity test in this phase requires the real URI.

**AI Agent Responsibilities:**
- Read `MONGODB_URI` / `MONGODB_DB_NAME` only from environment variables, never hardcoded.
- Do not rename the three collections or their field names from Section 2.3.
- Add only the indexes specified below — no speculative extra indexes without noting why in Phase 12.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Create `apps/backend` Python virtual environment and a starter `requirements.txt` with `motor`, `pymongo`, `python-dotenv`, `pydantic`.
   ✅ TEST: `pip install -r requirements.txt` succeeds inside the venv; `python -c "import motor, pymongo, pydantic"` runs with no error.
2. 🛑 Pause here and collect the real `MONGODB_URI` and confirmed database name from the user. Write the **name only** (no value) into `apps/backend/.env.example` as `MONGODB_URI=` and `MONGODB_DB_NAME=accessibility_auditor`, and mirror the names into the root `.env.example`. The real value goes only into `apps/backend/.env` (gitignored).
   ✅ TEST: both `.env.example` files contain the key names with empty values; `apps/backend/.env` (local, untracked) contains the real values; `git status` does not show any `.env` file.
3. Create `apps/backend/app/db.py`: an async Motor client singleton reading both env vars, exposing `get_db()`. Create `apps/backend/scripts/check_db_connection.py` as the runnable check for this step.
   ✅ TEST: `python scripts/check_db_connection.py` calls `await db.command("ping")` against the real cluster and prints `{'ok': 1.0}`.
4. Define Pydantic models for `scans`, `violations`, and (stub only) `users`, mirroring the field names in Section 2.3 exactly.
   ✅ TEST: instantiate each model with a valid sample dict (passes) and with a required field missing (raises a validation error) — both behaviors confirmed in a quick script, not assumed.
5. Create an index-setup script: `violations.scan_id` (ascending), `scans.url`, `scans.scanned_at` (descending).
   ✅ TEST: run the script, then query `db.violations.index_information()` / `db.scans.index_information()` and confirm the expected indexes are listed.
6. Insert a throwaway test document into each collection, read it back, then delete it. Implement this as `apps/backend/tests/test_db_connection.py` — the same file the Phase-Level Validation gate below runs.
   ✅ TEST: document count in each collection before the test equals the count after — no orphaned test data left in the real cluster.

**Commands (Quick Reference):**
```bash
cd apps/backend
python3 -m venv venv && source venv/bin/activate
pip install motor pymongo python-dotenv pydantic
pip freeze > requirements.txt
python scripts/check_db_connection.py
python scripts/create_indexes.py
```

**Files to Create/Modify:**
- `apps/backend/requirements.txt`
- `apps/backend/app/db.py`
- `apps/backend/app/models.py`
- `apps/backend/scripts/check_db_connection.py`
- `apps/backend/scripts/create_indexes.py`
- `apps/backend/tests/test_db_connection.py`
- `apps/backend/.env.example` (add `MONGODB_URI`, `MONGODB_DB_NAME`)
- root `.env.example` (mirror the same two names)

**Phase-Level Validation & Testing:**
Run `apps/backend/tests/test_db_connection.py` (a real pytest, not a manual script) asserting: connection succeeds, insert/read/delete round-trips cleanly on all three collections, and all expected indexes exist. All assertions must pass against the real Atlas cluster, not a mock, before Phase 2 begins.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Auth failure on connect | Password likely has special characters that need URL-encoding in the URI |
| Connection times out | IP not whitelisted in Atlas Network Access — add the correct IP/range |
| Collections appear empty after "successful" writes | Wrong `MONGODB_DB_NAME` — Atlas silently creates a new empty DB with a typo'd name |
| TLS/SSL handshake errors | Outdated `pymongo`/`motor` version — upgrade the driver |

**Phase Completion Checklist:**
- [ ] Real `MONGODB_URI` obtained from user and stored only in untracked `.env`
- [ ] Connectivity verified against the live cluster
- [ ] All three collections exist with spec-correct field names
- [ ] Required indexes created and confirmed
- [ ] `test_db_connection.py` passes

---

## Phase 2 — Scanner Service (Node.js + Playwright + axe-core)

**Goal:** A standalone microservice that takes a URL and returns a structured violation list (rule ID, severity, DOM snippet, WCAG reference) — the first box in the architecture diagram, runnable on its own before anything else depends on it.

**Prerequisites:** Phase 0 complete. Node.js 18+.

**User Action Required:** None — no external credentials are needed for this phase. Confirm `npm` as the package manager unless the user states a preference otherwise.

**AI Agent Responsibilities:**
- Use exactly Playwright + `@axe-core/playwright`. No substitute browser-automation library.
- Always close the browser context, including on error paths (`try/finally`) — Render's free tier has limited RAM, and a leaked context is the single most likely production failure mode for this service.
- Block obviously dangerous targets (localhost, private IP ranges) at the input-validation layer to prevent the scanner being used as an open SSRF proxy.
- Listen on `process.env.PORT`, falling back to `4000` only when `PORT` is unset — Render assigns its own port at deploy time and health-checks whatever the platform tells the app to bind to, not a value hardcoded in the app. Getting this wrong is a real, common cause of failed Render deploys, not just a style preference.

**Implementation Steps & Mandatory Per-Step Testing:**

1. `npm init -y` in `services/scanner`; install `express`, `@axe-core/playwright`, `playwright`, `cors`, `dotenv`; add `"scripts": {"dev": "node src/server.js", "start": "node src/server.js"}` to `package.json`.
   ✅ TEST: `npm ls --depth=0` shows all five packages; `npx playwright --version` runs; `npm run dev` (once `src/server.js` exists in step 5) actually starts the process rather than failing with "missing script."
2. `npx playwright install --with-deps chromium`.
   ✅ TEST: a one-off Node script launches Chromium, navigates to `https://example.com`, reads the page title, and closes the browser — confirmed by console output, not assumed.
3. Implement `src/severityMap.js` mapping axe `impact` values (`critical`/`serious`/`moderate`/`minor`) straight through, and a WCAG-tag extractor that pulls `wcag2a`/`wcag2aa`/`wcag21aa`/`wcag22aa`-style tags off each axe result into a clean `wcag_ref`.
   ✅ TEST: feed a sample raw axe result object through the mapper and assert the output has exactly the fields the spec requires.
4. Implement `src/scan.js` → `runScan(url)`: launches a browser, opens a context/page, navigates with a sane timeout, runs `AxeBuilder(...).analyze()`, maps violations through step 3's helpers, and **always** closes the context in a `finally` block.
   ✅ TEST: run against a real public page known to have accessibility issues; confirm the returned array is non-empty and every item has `{ruleId, severity, wcagRef, domSnippet}`.
5. Implement `src/server.js`: load `dotenv` first, then an Express app listening on `process.env.PORT || 4000`, with `GET /healthz` and `POST /scan { url }`, including URL validation (reject non-http(s), reject localhost/private-IP targets).
   ✅ TEST: `curl /healthz` → `200 {"status":"ok"}`; `curl -X POST /scan` with a real URL → `200` + violations array; with a malformed URL → `400`; with `http://localhost:...` → blocked with a clear `4xx`; confirm `PORT=5001 npm start` actually binds to 5001, not 4000.
6. Add an in-memory concurrency guard rejecting a second `/scan` while one is in flight for the process.
   ✅ TEST: fire two concurrent `POST /scan` requests; confirm the second receives a `429`-style "scan in progress" response rather than the process crashing or both running simultaneously; log `process.memoryUsage()` before and after to confirm memory returns to baseline.

**Commands (Quick Reference):**
```bash
cd services/scanner
npm init -y
npm install express @axe-core/playwright playwright cors dotenv
npx playwright install --with-deps chromium
npm run dev
curl http://localhost:4000/healthz
curl -X POST http://localhost:4000/scan -H "Content-Type: application/json" -d '{"url":"https://example.com"}'
```

**Files to Create/Modify:**
- `services/scanner/package.json`
- `services/scanner/src/server.js`
- `services/scanner/src/scan.js`
- `services/scanner/src/severityMap.js`
- `services/scanner/.env.example` (add `PORT=` with an empty value; `PORT` is auto-injected by Render at deploy time but must be listed here so local runs can override it)

**Phase-Level Validation & Testing:**
Run the scanner against three real public URLs of varying quality (a well-built site, a clearly inaccessible one, and a simple page like `example.com`). Confirm: every response is spec-shaped; total response time is well under the product's 15-second end-to-end target (the scanner alone should be a small fraction of that budget); server logs show no unhandled promise rejections across all three runs; the Chromium process count returns to zero after each run.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Missing system libraries for Chromium | Use `--with-deps` on install, or the official Playwright Docker base image later in Phase 9 |
| Timeout on JS-heavy single-page apps | Increase navigation timeout; fall back from `networkidle` to `domcontentloaded` if needed |
| Memory creeps up across repeated scans | Audit that every code path actually reaches the `finally` that closes the context |
| CORS errors hit when called directly from a browser | Not expected in production — only the backend (Phase 7) calls the scanner server-to-server |

**Phase Completion Checklist:**
- [ ] Service runs standalone with no external credentials
- [ ] `/healthz` green
- [ ] `/scan` returns spec-shaped JSON for 3+ real URLs
- [ ] Browser context always closes, verified under concurrent load
- [ ] Concurrency guard tested and working

---

## Phase 3 — Fix-Generation: Deterministic Contrast Fixer

**Goal:** A fully deterministic (no AI call) function that nudges a failing foreground/background color pair to meet the WCAG contrast threshold (4.5:1 normal text / 3:1 large text/UI), and self-verifies its own output before returning it.

**Prerequisites:** Phase 2's scanner must pass through the raw foreground/background color data axe-core already captures for `color-contrast` violations. If the current scanner output doesn't include this, extend `src/severityMap.js` now to pass through axe's `nodes[].any[].data` payload for this rule, then re-run Phase 2's validation test to confirm nothing else broke.

**User Action Required:** None — this step uses no external API and no credentials.

**AI Agent Responsibilities:**
- Implement the WCAG relative-luminance and contrast-ratio formulas directly — no opaque third-party color library standing in for the math, so the calculation stays auditable.
- The adjuster must re-check its own output's contrast ratio before returning a "fixed" value. It must never return a color it hasn't itself verified.
- If the threshold can't be hit within a bounded number of iterations without producing a visually broken extreme, return a "needs manual review" result instead of a fake pass.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Create `apps/backend/app/fixers/contrast.py` with `relative_luminance(rgb)` and `contrast_ratio(rgb1, rgb2)`.
   ✅ TEST: unit test against known reference pairs (e.g., black-on-white must compute to 21:1) — assert to two decimal places.
2. Implement `adjust_for_contrast(fg_rgb, bg_rgb, target_ratio, large_text: bool)` — adjusts the HSL lightness of the foreground in bounded steps (cap ~50 iterations) until the ratio is met, or returns `None`/manual-review on failure.
   ✅ TEST: feed a real failing pair (e.g., light gray on white) and assert the returned color, when passed back through `contrast_ratio`, is ≥ the target; assert the iteration count stays bounded on a deliberately near-impossible pair (e.g., mid-gray on mid-gray).
3. Implement `generate_contrast_fix(violation)` returning the `ai_fix`-shaped dict: `{type: "contrast", original, fixed, explanation, confidence: 1.0}` — confidence is a fixed constant here, never a guessed/variable number, since the method is deterministic.
   ✅ TEST: pass a full violation dict (as produced after Phase 2's data passthrough) through this function and assert all required keys are present and the fixed color independently re-verifies.
4. Add an "already compliant" short-circuit: if the original pair already meets threshold, return it unchanged with an explanatory note rather than perturbing a passing color.
   ✅ TEST: feed an already-passing pair; assert `fixed == original` and the explanation says so.

**Commands (Quick Reference):**
```bash
cd apps/backend
source venv/bin/activate
pytest app/fixers/tests/test_contrast.py -v
```

**Files to Create/Modify:**
- `apps/backend/app/fixers/contrast.py`
- `apps/backend/app/fixers/tests/test_contrast.py`
- (cross-phase) `services/scanner/src/severityMap.js` — only if contrast data passthrough needs adding

**Phase-Level Validation & Testing:**
Run the function against the actual violation list produced by the real Phase 2 scanner on a known low-contrast public page. Confirm 100% of the returned fixes independently re-verify at or above threshold, and that no input (including edge cases like rgba colors or already-passing pairs) raises an unhandled exception.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Result oscillates near the threshold due to rounding | Require ratio ≥ target + a small epsilon (e.g., 0.05) instead of exact equality |
| `rgba()` values break the parser | Flatten alpha against the background color before computing luminance |
| 3:1 threshold applied where 4.5:1 was correct (or vice versa) | Confirm the violation's own axe data flags large-text/UI status — never hardcode one threshold for everything |

**Phase Completion Checklist:**
- [ ] Formulas unit-tested against known reference values
- [ ] Adjuster self-verifies every output before returning it
- [ ] "Already compliant" and "manual review fallback" paths both tested
- [ ] Validated against at least one real scanned page's actual violations

---

## Phase 4 — Fix-Generation: AI Alt-Text (Vision-Language Model)

**Goal:** Contextual alt-text generation for missing/poor `alt` violations, using an actual image + surrounding page text sent to a vision-capable model — never fabricated text.

**Prerequisites:** Phase 2's scanner output must include the image `src` and nearby text context for `image-alt`-type violations; extend the scanner now if it doesn't, re-running Phase 2's validation afterward.

**🛑 User Action Required (STOP — required before any real API call):**
- Confirm `AI_PROVIDER` for this build: `gemini` (primary, recommended default) or `openrouter` (fallback) — see Section 3.1. The agent asks and records the choice; it does not default silently even though `gemini` is recommended.
- Provide the corresponding key: `GEMINI_API_KEY` (Google AI Studio free tier) if `AI_PROVIDER=gemini`, or `OPENROUTER_API_KEY` plus a confirmed vision-capable `OPENROUTER_MODEL` slug (a current `:free` model from `openrouter.ai/models`) if `AI_PROVIDER=openrouter`.
- Approve a `MAX_IMAGES_PER_SCAN` cap (a concrete number) before the agent writes any code that would call the real API in a loop. Free-tier calls aren't billed per request, but they are rate- and quota-limited, so an unbounded loop still breaks the pipeline, not just a budget.

**AI Agent Responsibilities:**
- Never call the configured provider's API without the corresponding key already present in the environment — fail fast with a clear error rather than silently skipping or faking a response. If `AI_PROVIDER` is unset or holds any value other than `gemini`/`openrouter`, raise a configuration error per Section 3.1 — never silently default to one provider.
- Always send real surrounding text context with the image, not just the bare image.
- Enforce the agreed cap; anything beyond it is marked "skipped — manual review (image cap reached)," not silently dropped.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Add `google-genai` to `requirements.txt` — the current official Gemini SDK. OpenRouter needs no extra package; it's reached via the existing `httpx` dependency over its OpenAI-compatible REST endpoint (Section 3.1).
   ✅ TEST: `pip install` succeeds; `python -c "from google import genai"` runs with no error.
2. 🛑 Pause and collect the real key(s) for the chosen provider from the user. Add the **name(s) only** to `.env.example`; the real value goes only into untracked `.env`.
   ✅ TEST: `.env.example` has the key name(s) with empty values; the real key never appears in any tracked file (`git status` clean, `grep` across tracked files returns nothing).
3. Implement `apps/backend/app/ai_provider.py`: reads `AI_PROVIDER`, validates it is exactly `gemini` or `openrouter`, and exposes the dispatch functions both fixers call (a vision-capable completion for Phase 4, a text completion for Phase 5) per Section 3.1's selection logic. Raise the configuration error immediately on import if `AI_PROVIDER` is missing or unrecognized — don't defer it to the first call.
   ✅ TEST: with `AI_PROVIDER` unset, and again set to a junk value, importing this module raises the configuration error both times; with it set to `gemini` or `openrouter`, import succeeds.
4. Implement `apps/backend/app/fixers/alt_text.py` → `generate_alt_text(image_url, surrounding_text, max_length=125)`: fetches the image (timeout + size-cap + content-type check), calls `ai_provider`'s vision function with a prompt requiring concise, contextual, non-redundant alt text (no "image of"/"picture of" boilerplate), returns the `ai_fix` dict.
   ✅ TEST: call against one real test image + real surrounding text using whichever provider is configured; assert a non-empty string ≤125 chars with no banned boilerplate phrases.
5. Add structured fallback handling for: image fetch failure, unsupported format, API timeout, API auth failure, and API rate-limit/quota errors (expected in normal use on a free tier, not just a misconfiguration symptom) — each must downgrade to a "needs manual review" object, never crash the pipeline.
   ✅ TEST: simulate each failure mode individually (bad URL, temporarily invalid key, a forced 429) and confirm a graceful fallback object every time, with the error logged.
6. Enforce the agreed `MAX_IMAGES_PER_SCAN` cap.
   ✅ TEST: feed more images than the cap; confirm only the capped number trigger a real API call and the rest get the skipped marker — verify via call-count logging, not just trusting the output shape.

**Commands (Quick Reference):**
```bash
cd apps/backend
pip install google-genai   # OpenRouter fallback needs no extra package — it's called via httpx
pytest app/fixers/tests/test_alt_text.py -v
```

**Files to Create/Modify:**
- `apps/backend/app/ai_provider.py` (new — shared provider resolver, also used by Phase 5)
- `apps/backend/app/fixers/alt_text.py`
- `apps/backend/app/fixers/tests/test_alt_text.py`
- `.env.example` (add `AI_PROVIDER`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `MAX_IMAGES_PER_SCAN`)

**Phase-Level Validation & Testing:**
Run against the actual missing-alt violations from a real scanned page. Manually review every generated alt text for contextual accuracy and log the results immediately into `docs/benchmarks.md` (created in Phase 11) — this manual review is the direct input to the project's "% fix accepted" success metric, so start collecting it now rather than retroactively.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Rate limiting / 429s | Retry with backoff, capped at 2 retries, then fall back to manual review |
| Images blocked by auth/CORS when fetched server-side | Fall back to manual review — never fabricate a description without the actual image |
| Decorative icons/SVGs flagged unnecessarily | Filter known decorative patterns (tiny size, `role="presentation"`) before spending an API call on them |
| Free-tier daily quota exhausted mid-scan | Surface a clear error distinguishing this from a code bug; suggest switching `AI_PROVIDER` to the fallback or waiting for quota reset — never retry indefinitely |

**Phase Completion Checklist:**
- [ ] `AI_PROVIDER` and the corresponding key(s) confirmed by the user before the first real call
- [ ] `ai_provider.py` resolver tested against both a valid and an invalid `AI_PROVIDER` value
- [ ] Image cap enforced and verified by call count
- [ ] All failure paths — including free-tier rate-limit/quota errors — tested and degrade gracefully
- [ ] At least 5 real fixes generated and logged for benchmark review

---

## Phase 5 — Fix-Generation: AI ARIA / Semantic Fixer

**Goal:** An LLM-generated, minimally-scoped HTML fix for ARIA/semantic violations, grounded in real ARIA Authoring Practices Guide (APG) patterns, with a one-line plain-English explanation — never an invented attribute, never an unrelated refactor.

**Prerequisites:** Phase 4's provider decision exists.

**🛑 User Action Required:** Confirm whether to reuse Phase 4's API key/provider for this text-only task, or use a different (e.g., cheaper, non-vision) model. If different, stop and collect that key before writing provider-specific code.

**AI Agent Responsibilities:**
- Ground every suggested fix in an actual APG pattern — never invent a non-existent ARIA attribute or role.
- Cap the diff to the smallest change that resolves the cited violation.
- Always cite the relevant WCAG/ARIA reference in the explanation.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Create `apps/backend/app/data/aria_patterns.json` mapping common axe rule IDs (`aria-allowed-attr`, `button-name`, `landmark-one-main`, `region`, `label`, etc.) to the relevant APG pattern name and a canonical correct markup skeleton.
   ✅ TEST: JSON parses cleanly; spot-check 5 entries against the actual current W3C ARIA APG content for accuracy rather than relying on memory.
2. Implement `apps/backend/app/fixers/aria_fix.py` → `generate_aria_fix(violation)`: builds a prompt with the original DOM snippet plus the matched pattern skeleton (if found), instructs strict JSON output (`{fixed_snippet, explanation}`), calls the LLM, parses defensively (retry once on malformed JSON, then fall back to manual review).
   ✅ TEST: run against 3 different real ARIA violations from an actual scanned page; assert the JSON parses, the snippet is plausible valid HTML on manual read, and the explanation cites the correct criterion.
3. Add an HTML-syntax sanity check on the model's output (parse with a DOM parser) before accepting it as a fix.
   ✅ TEST: deliberately truncate a model response in a test harness and confirm the sanity check rejects it and triggers the fallback rather than shipping broken markup.

**Commands (Quick Reference):**
```bash
cd apps/backend
pytest app/fixers/tests/test_aria_fix.py -v
```

**Files to Create/Modify:**
- `apps/backend/app/data/aria_patterns.json`
- `apps/backend/app/fixers/aria_fix.py`
- `apps/backend/app/fixers/tests/test_aria_fix.py`

**Phase-Level Validation & Testing:**
Run against a real page with 5+ ARIA/semantic violations; log every fix to `docs/benchmarks.md` for the same manual-accuracy-review pipeline used in Phase 4.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Model wraps JSON in markdown code fences | Strip fences before parsing |
| Fix is valid but stylistically inconsistent (indentation, quote style) | Acceptable — note as cosmetic, not a blocker |
| Rule ID has no APG table entry | Still attempt a fix using general WCAG knowledge, but the explanation must say so explicitly so reviewers treat it as lower-confidence |

**Phase Completion Checklist:**
- [ ] APG reference table created and spot-verified against the real source
- [ ] JSON-mode parsing robust with a tested fallback path
- [ ] HTML sanity check in place and tested against malformed output
- [ ] 5+ real fixes logged for benchmark review

---

## Phase 6 — Scoring Engine

**Goal:** A pure, auditable implementation of the 🔒 severity-weighted score (before and projected-after), with the weight table as a single named constant — not magic numbers scattered through the code.

**Prerequisites:** Phases 2–5 producing violations and `ai_fix` objects.

**🛑 User Action Required:** One product decision, asked once: should `score_after` assume *all* generated fixes are accepted (an optimistic, demo-friendly number), or only fixes that passed their own internal verification (Phase 3's self-checked contrast, Phase 5's syntax-checked ARIA, Phase 4's non-fallback alt-text)? The latter is recommended for credibility against the project's own success-metrics goal, but it is the user's call — get an explicit answer before implementing either way.

**AI Agent Responsibilities:**
- Implement the weight table from Section 2.5 exactly — no adjustment without approval.
- Make the weights a single named, documented constant.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Create `apps/backend/app/scoring.py` with `SEVERITY_WEIGHTS = {"critical": 10, "serious": 7, "moderate": 4, "minor": 2}` and `compute_score(violations) -> int`.
   ✅ TEST: unit test with a synthetic violation list of known severities; assert the sum matches a hand-calculated total.
2. Implement `compute_before_after(violations_with_fixes)` per the user's Phase 6 decision: `score_before` over all violations, `score_after` over only the violations whose fix did *not* pass internal verification (or over none, if the user chose the optimistic variant).
   ✅ TEST: a synthetic case where 2 of 5 violations have a verified fix — assert `score_after` equals the weight-sum of the remaining 3 only (or the user's chosen alternative behavior).
3. Persist `score_before`/`score_after` onto the `scans` document using exactly those field names from Section 2.3.
   ✅ TEST: round-trip a synthetic scan through MongoDB (Phase 1's connection) and read back identical numeric values.

**Commands (Quick Reference):**
```bash
cd apps/backend
pytest app/tests/test_scoring.py -v
```

**Files to Create/Modify:**
- `apps/backend/app/scoring.py`
- `apps/backend/app/tests/test_scoring.py`

**Phase-Level Validation & Testing:**
Run the full Phase 2→6 pipeline on one real public URL end-to-end. Confirm the invariant `score_after <= score_before` always holds (if a "fix" ever increases the score, that's a bug — fail loudly, don't average it away), and that both numbers persist correctly in MongoDB.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Unrecognized severity value (e.g., axe's `info` level) | Default to 0 weight and log a warning — never crash, never silently swallow without a trace |
| Same DOM node tripping multiple rules looks like double-counting | This is correct per spec — each violation is its own document and counts separately; do not deduplicate without approval |

**Phase Completion Checklist:**
- [ ] Weights match Section 2.5 exactly, defined as one named constant
- [ ] `score_after <= score_before` invariant holds on real data
- [ ] Fields persisted with exact schema names
- [ ] Unknown-severity edge case handled without crashing

---

## Phase 7 — Backend Orchestration API (FastAPI)

**Goal:** The single public REST contract the frontend calls — internally ties the scanner, all three fixers, and the scoring engine together, persists to MongoDB, and returns one assembled result.

**Prerequisites:** Phases 1–6 each individually verified and passing their own tests.

**🛑 User Action Required:** Confirm the CORS origins to allow — at minimum `http://localhost:3000` for local development; the production frontend domain gets added once it exists (Phase 10). The agent does not leave a wildcard `*` origin in anything intended for production.

**AI Agent Responsibilities:**
- Isolate failures per-violation (`try/except` around each fixer call) — one failed fix-generation must never abort the whole scan; it downgrades that single violation to manual-review and the rest of the pipeline continues.
- Respect the product's ~15-second end-to-end target where realistic. If real AI latency on an image-heavy page makes that target unrealistic, the agent surfaces this explicitly to the user rather than silently exceeding it or quietly lowering the bar.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Add `fastapi`, `uvicorn`, `httpx` to `requirements.txt`; create `apps/backend/app/main.py` with CORS middleware (origins from env) and `GET /healthz`.
   ✅ TEST: `uvicorn app.main:app --reload`; `curl /healthz` → `200`.
2. Create `apps/backend/app/routes/scans.py` → `POST /api/scans {url}`: validates the URL, calls the scanner over HTTP (`SCANNER_SERVICE_URL`), fans each violation out to its matching fixer (Phases 3–5) with bounded concurrency for cost control, computes scores (Phase 6), persists `scans` + `violations` documents (Phase 1), returns the assembled JSON.
   ✅ TEST: with the scanner running locally and real AI keys present, `curl -X POST /api/scans` with a real public URL; assert the response includes `scanId, url, scoreBefore, scoreAfter, violations[]` (each with an `ai_fix`); independently query MongoDB to confirm the documents actually exist — don't just trust the API's own response.
3. Add `GET /api/scans/{scan_id}` reading back from MongoDB.
   ✅ TEST: fetch the scan created in step 2; assert byte-identical violation data to what was returned at creation time.
4. Add a global exception handler (clean structured JSON errors, never a raw stack trace to the client) and structured request logging (request id, url, duration).
   ✅ TEST: stop the scanner service, hit `POST /api/scans`, confirm a clean `502`-style structured error rather than a 500 crash dump.

**Commands (Quick Reference):**
```bash
cd apps/backend
pip install fastapi uvicorn httpx
uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/healthz
curl -X POST http://localhost:8000/api/scans -H "Content-Type: application/json" -d '{"url":"https://example.com"}'
```

**Files to Create/Modify:**
- `apps/backend/app/main.py`
- `apps/backend/app/routes/scans.py`
- `apps/backend/app/config.py`
- `.env.example` (add `SCANNER_SERVICE_URL`, `CORS_ALLOWED_ORIGINS`, `BACKEND_PORT`)

**Phase-Level Validation & Testing:**
True end-to-end run: scanner (Phase 2) + this backend running together locally, `POST /api/scans` against 3 different real public URLs of varying complexity. Measure and log latency for each (this seeds Phase 11's latency metric). Confirm zero unhandled exceptions across all three, and that MongoDB has exactly one `scans` document plus N `violations` documents per run — no duplicates, no orphans.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Scanner timeout cascades into a hung request | Add a per-call timeout with a clear error surfaced to the caller |
| Concurrent VLM calls exceed the agreed cost cap | Enforce the concurrency/cost limit at this orchestration layer, not only inside Phase 4's module — this is where real fan-out concurrency happens |
| `scans.status` doesn't reflect what actually happened | Always set it accurately: `completed`, `completed_with_errors`, or `failed` |

**Phase Completion Checklist:**
- [ ] Single `POST /api/scans` exercises the full pipeline end-to-end
- [ ] `GET /api/scans/{id}` round-trips correctly
- [ ] Errors are structured JSON only, never raw stack traces
- [ ] Latency logged for 3 real URLs
- [ ] `status` field accurate across success, partial-failure, and failure paths

---

## Phase 8 — Frontend Dashboard (Next.js + Tailwind)

**Goal:** A single URL input that produces a live-updating scan and a results dashboard grouped by severity with a real before/after diff viewer — no login wall, per the locked scope.

**Prerequisites:** Phase 7 backend reachable locally.

**User Action Required:** None for local development. (`NEXT_PUBLIC_API_BASE_URL` for production is confirmed in Phase 10.)

**AI Agent Responsibilities:**
- Do not add an auth/login flow — explicitly out of scope (Section 2.4).
- The diff viewer must show real original-vs-fixed content for every fix, never a bare "fixed ✅" badge — this is the project's stated differentiator and is non-negotiable.

**Implementation Steps & Mandatory Per-Step Testing:**

1. `npx create-next-app` (TypeScript, Tailwind, App Router) at `apps/frontend`.
   ✅ TEST: `npm run dev` boots the starter page at `localhost:3000` with no errors.
2. Build the URL input (`app/page.tsx` + `ScanForm.tsx`): single input, submit calls the backend's `POST /api/scans`, shows a loading state.
   ✅ TEST: manual browser run — submit a known-good URL, observe the loading state, then results render with no console errors.
3. Build `ResultsDashboard.tsx`: violations grouped by severity with counts, plus the score-before/after summary.
   ✅ TEST: with a real scan response loaded, cross-check the on-screen counts against the raw `curl` output from Phase 7 — they must match exactly.
4. Build `DiffViewer.tsx` per violation: original vs. fixed, plain-language explanation, confidence indicator, and a visually distinct "needs manual review" state.
   ✅ TEST: confirm at least one real example of each fix type (contrast/alt-text/ARIA) plus the manual-review fallback all render with real data, not placeholder text.
5. Add a report-export button (JSON download + a print-friendly summary view).
   ✅ TEST: click export, parse the downloaded JSON, confirm it matches the on-screen data exactly.
6. Run an accessibility self-check on the dashboard itself (axe-core browser extension or equivalent against your own running page) and fix anything it finds.
   ✅ TEST: zero critical/serious violations on your own results page before calling this phase done.

**Commands (Quick Reference):**
```bash
cd apps
npx create-next-app@latest frontend --typescript --tailwind --app
cd frontend
npm run dev
```

**Files to Create/Modify:**
- `apps/frontend/app/page.tsx`
- `apps/frontend/app/components/ScanForm.tsx`
- `apps/frontend/app/components/ResultsDashboard.tsx`
- `apps/frontend/app/components/DiffViewer.tsx`
- `apps/frontend/app/lib/api.ts`
- `apps/frontend/.env.local.example`

**Phase-Level Validation & Testing:**
Full manual click-through of the entire user journey (paste URL → loading → grouped results → expand a diff → export) against the real local backend, for at least 2 different real public URLs. No console errors/warnings. Lighthouse accessibility score on the dashboard itself ≥ 95.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| CORS errors calling the backend | Fix the backend's `CORS_ALLOWED_ORIGINS` (Phase 7) — don't work around it from the frontend |
| Page unresponsive on a heavily-violating site (100+ items) | Paginate or virtualize the violation list |
| Slow first response (only relevant once deployed) | Render's free-tier cold start — handled in Phase 10's UX note, not a frontend bug |

**Phase Completion Checklist:**
- [ ] No-login flow works end-to-end locally
- [ ] Diff viewer shows real before/after for all 3 fix types plus the fallback state
- [ ] Self-audit of the dashboard itself is clean
- [ ] Export verified byte-accurate against on-screen data

---

## Phase 9 — Containerization (Docker)

**Goal:** Dockerize the scanner worker exactly as the architecture diagram specifies, using an official Playwright base image so system dependencies don't drift.

**Prerequisites:** Phase 2 scanner working locally and passing its tests. Docker installed.

**User Action Required:** Confirm whether the FastAPI backend should also be containerized, or deployed as a native Render Python service (recommended — only the scanner has the Playwright/Chromium dependency the diagram calls out for Docker specifically).

**AI Agent Responsibilities:**
- Use the official Playwright Docker base image rather than hand-assembling an apt package list.
- The container must preserve the same close-context-per-scan discipline from Phase 2 — Docker does not fix a memory leak in application logic.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Create `services/scanner/Dockerfile`: look up the current Playwright image tag at `mcr.microsoft.com/playwright` (or `hub.docker.com/_/microsoft-playwright`) and use `FROM mcr.microsoft.com/playwright:<current-version>-jammy`, copy package files, `npm ci`, copy `src/`, `EXPOSE 4000`, `CMD ["node", "src/server.js"]`.
   ✅ TEST: `docker build -t scanner-service .` completes with no errors.
2. Run the container.
   ✅ TEST: `curl http://localhost:4000/healthz` and `curl -X POST .../scan` from the host succeed, matching the native (non-Docker) Phase 2 results in shape.
3. (Optional) Create a root `docker-compose.yml` wiring the scanner (and, if containerized, the backend) for convenient local full-stack runs.
   ✅ TEST: `docker compose up` brings the scanner up and reachable at its compose service name from another composed service.
4. Add `services/scanner/.dockerignore` (`node_modules`, `.git`, etc.).
   ✅ TEST: check resulting image size is sane (no hard threshold — just confirm it isn't bloated from a missing ignore rule).

**Commands (Quick Reference):**
```bash
cd services/scanner
docker build -t scanner-service .
docker run -p 4000:4000 --env-file .env scanner-service
curl http://localhost:4000/healthz
```

**Files to Create/Modify:**
- `services/scanner/Dockerfile`
- `services/scanner/.dockerignore`
- `docker-compose.yml` (optional, root)

**Phase-Level Validation & Testing:**
Re-run the same 3-URL test set from Phase 2's validation against the Dockerized container instead of the native process. Outputs must match in shape, with latency in a reasonable range of the native run.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Missing shared libraries for Chromium | Confirm the official Playwright base image is actually in use, not a generic `node:` image |
| Container OOM under memory pressure | Re-confirm the close-context discipline is present in the code that's actually inside the image — rebuild with `--no-cache` once if results look stale |

**Phase Completion Checklist:**
- [ ] Image builds clean
- [ ] Container passes the same functional tests as the native Phase 2 service
- [ ] Compose file (if added) brings up a working local stack
- [ ] Image size sanity-checked

---

## Phase 10 — Deployment (Vercel + Render)

**Goal:** Frontend live on Vercel, backend API and scanner worker live on Render as separate services, wired together with real production env vars, against the MongoDB Atlas cluster already live since Phase 1.

**Prerequisites:** All prior phases passing locally. Code pushed to a GitHub repository.

**🛑 User Action Required (multiple items — all required before deploying):**
- A GitHub repository with this code pushed. The agent can help initialize the remote and push, but the user must create the empty repo on GitHub and grant push access — the agent does not invent a repository.
- A Vercel account connected to that repo, and a decision on deployment path: Git-integration UI flow (recommended, simplest) vs. CLI with a Vercel token. Ask before proceeding.
- A Render account with two services pointing at the repo (scanner worker, backend API), and the same UI-vs-CLI/token decision.
- Every production secret entered directly into the Vercel/Render dashboards by the user: `MONGODB_URI`, the AI provider key(s), `CORS_ALLOWED_ORIGINS`, `SCANNER_SERVICE_URL` (pointing at the deployed scanner's Render URL), `NEXT_PUBLIC_API_BASE_URL` (pointing at the deployed backend's Render URL). The agent lists every required variable (Appendix A) and waits for confirmation each is set — it never guesses a value or proceeds without one.

**AI Agent Responsibilities:**
- Never write a real secret value into code, commit history, or this guide — only ever reference env var names.
- Run a final repo-wide secret scan before the first push.
- Re-run the Phase 2 / Phase 7 / Phase 8 validation test sets against the **live** URLs, not just locally, before declaring deployment done.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Confirm `.gitignore` excludes all `.env` files; scan tracked files for accidental secrets.
   ✅ TEST: `grep -RE "sk-|AIzaSy|mongodb\+srv://" $(git ls-files)` returns nothing.
2. Push to GitHub.
   ✅ TEST: repo visible on GitHub with the expected structure; no `.env` files present remotely.
3. On Render, create the scanner worker service (Docker deploy from `services/scanner`), set its env vars, deploy.
   ✅ TEST: `curl` the live `/healthz`; run one real `/scan` against the live URL and confirm the same response shape as local/Phase 9 tests.
4. On Render, create the backend API service, set all backend env vars (including the scanner's live URL from step 3), deploy.
   ✅ TEST: `curl` the live backend `/healthz`; `POST /api/scans` against the live backend with a real URL and confirm the full pipeline works in production, including a verified write into the real MongoDB Atlas cluster (check Atlas directly, not just the API response).
5. On Vercel, import the frontend, set `NEXT_PUBLIC_API_BASE_URL` to the live backend URL from step 4, deploy.
   ✅ TEST: open the live Vercel URL, run Phase 8's full user journey against production; if CORS errors appear, update the backend's `CORS_ALLOWED_ORIGINS` to include the live Vercel domain and redeploy the backend, then re-test.
6. Cold-start check: hit the Render backend after 20+ minutes of idle time and time the response.
   ✅ TEST: confirm the request eventually succeeds (Render's free-tier wake-up delay is expected behavior, not a bug); log the actual observed delay.

**Commands (Quick Reference):**
```bash
git remote add origin <your-repo-url>
git push -u origin main
# Render and Vercel deploys are driven from their dashboards or CLIs per the
# UI-vs-CLI decision made above — record which path was used in README.md.
curl https://<scanner>.onrender.com/healthz
curl https://<backend>.onrender.com/healthz
curl -X POST https://<backend>.onrender.com/api/scans -d '{"url":"https://example.com"}'
```

**Files to Create/Modify:**
- `render.yaml` (optional infra-as-code) or a documented manual dashboard config
- `vercel.json` (only if a custom build config is needed)
- `README.md` — add a "Live Demo" link section noting which deploy path (UI vs CLI) was used

**Phase-Level Validation & Testing:**
Full production smoke test: run the same 3-URL set used throughout the guide against the live Vercel+Render stack; confirm parity with local results (allowing for network latency differences); confirm MongoDB Atlas shows the new production scan documents.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| CORS rejects the deployed frontend | List the exact production Vercel domain (and preview-deployment domains, if used) in the backend's CORS config |
| Render cold start exceeds a caller's own timeout | Show a friendly "waking up the server, this can take up to a minute" state in the frontend rather than failing silently |
| Scanner OOMs under more memory pressure than seen locally | Re-confirm the context-closing discipline from Phases 2/9; consider trimming Playwright's resource usage further for production |

**Phase Completion Checklist:**
- [ ] All three live URLs reachable and healthy
- [ ] One full real production scan completed and independently verified in Atlas
- [ ] CORS correct for the production domain
- [ ] Cold-start behavior understood and handled gracefully in the UI
- [ ] Final secret scan confirms nothing leaked into the public repo

---

## Phase 11 — Benchmarking & Success Metrics

**Goal:** Produce the real, reproducible evidence numbers — number of sites benchmarked, average violations by severity, % of AI fixes accepted on manual review, average score improvement, scan latency — that turn this from a demo into a resume line with evidence behind it.

**Prerequisites:** A stable deployment (Phase 10) or a stable local environment. Either way, benchmarking uses **real public sites**, never synthetic fixtures.

**User Action Required:** Approve the specific list of real sites to benchmark. The agent suggests categories (a small-business site, an agency portfolio, a personal blog, etc.) but does not unilaterally pick and scan third-party sites at volume without the user's sign-off — this is also a basic courtesy/abuse-prevention boundary, not just a process step.

**AI Agent Responsibilities:**
- Only report an "accuracy %" backed by real, recorded manual-review judgments — never assert a number without a row in the benchmark table behind it.
- Archive every run's raw response so every published number is independently re-checkable.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Create `docs/benchmarks.md` with a results table template: site URL, date, violations by severity, `score_before`, `score_after`, scan latency, and fix-acceptance notes per reviewed fix.
   ✅ TEST: template renders as a valid Markdown table with a placeholder row.
2. Run the pipeline against each approved site; append one row per site; archive the raw JSON response in `docs/benchmarks/raw/<site>-<date>.json`.
   ✅ TEST: every table row has a corresponding raw file that can be opened and matches the row's numbers.
3. For a sample of generated fixes, the user manually marks each as accepted / rejected / needs-edit directly in `benchmarks.md`.
   ✅ TEST: tally accepted/total reviewed — this computed ratio *is* the accuracy percentage; it is never asserted independently of this tally.
4. Compute aggregate stats (N sites, average violations/site by severity, accuracy %, average score improvement, average latency) in a summary block at the top of `benchmarks.md`.
   ✅ TEST: hand-verify at least 2 of the aggregate numbers against the raw table rows.

**Commands (Quick Reference):**
```bash
# Example: run the live pipeline against one approved benchmark site
curl -X POST https://<backend>.onrender.com/api/scans -d '{"url":"<approved-site>"}' \
  | tee docs/benchmarks/raw/<site>-$(date +%F).json
```

**Files to Create/Modify:**
- `docs/benchmarks.md`
- `docs/benchmarks/raw/*.json`

**Phase-Level Validation & Testing:**
Every summary figure in `docs/benchmarks.md` must trace back to specific rows in the same document — no orphan claims with nothing backing them.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Target site blocks headless browsers (403s, bot-challenge pages) | Exclude it from the benchmark set and note why — don't force it |
| Small N makes percentages look more precise than they are | Report raw counts alongside percentages (e.g., "8/10, 80%") rather than the percentage alone |

**Phase Completion Checklist:**
- [ ] `docs/benchmarks.md` has real, reproducible data for an agreed N ≥ 5 real sites
- [ ] Accuracy % is computed from actual recorded manual review, not assumed
- [ ] Aggregate numbers hand-verified against raw rows

---

## Phase 12 — Documentation & Maintenance Protocol

**Goal:** Keep this guide and its supporting docs accurate as the single source of truth for the lifetime of the project — a code change without a corresponding doc update is incomplete work, not a follow-up task.

**Prerequisites:** All prior phases complete.

**User Action Required:** Optionally decide on an issue-tracking convention (e.g., GitHub Issues) for future changes — not blocking.

**AI Agent Responsibilities:**
- Any time architecture, schema, env vars, or phase steps change from what's written in this guide, update `docs/guide.md` itself in the same unit of work as the code change.

**Implementation Steps & Mandatory Per-Step Testing:**

1. Write the root `README.md`: links to `docs/guide.md` (canonical) and `docs/benchmarks.md` (metrics), with a short, non-duplicated project description.
   ✅ TEST: README renders correctly on GitHub; all links resolve.
2. Create `CHANGELOG.md`; log each phase's completion date and any user-approved deviations from this guide.
   ✅ TEST: entries exist for Phases 0–11 retroactively once this phase runs.
3. Walk every "Files to Create/Modify" entry across all 12 phases and confirm each file actually exists in the repo.
   ✅ TEST: a checklist pass, phase by phase, confirming presence — any gap gets either built or explicitly logged as a deferred item in `CHANGELOG.md`.

**Commands (Quick Reference):**
```bash
git log --oneline --all
find . -name "*.md" -not -path "*/node_modules/*"
```

**Files to Create/Modify:**
- `README.md`
- `CHANGELOG.md`

**Phase-Level Validation & Testing:**
The ultimate test of this guide: a fresh clone of the repository, following only `docs/guide.md` from Phase 0 forward with credentials re-supplied by the user, must reach a working local dev environment. If it doesn't, the guide — not just the code — has a defect to fix.

**Common Issues & Fixes:**

| Issue | Fix |
|---|---|
| Guide drifts from actual code over time | Schedule a guide-vs-code diff review before each new contributor or each deploy |
| Stale env var docs cause onboarding friction | Appendix A is updated the moment any env var is added, renamed, or removed anywhere in the codebase |

**Phase Completion Checklist:**
- [ ] `README.md` and `CHANGELOG.md` present and accurate
- [ ] Every file from every phase verified present
- [ ] This guide re-validated against a clean clone

---

## Appendix A — Environment Variable Reference

| Variable | Used by | Required for | Notes |
|---|---|---|---|
| `MONGODB_URI` | backend | Phase 1+ | Real value lives only in untracked `.env` / hosting dashboard secrets |
| `MONGODB_DB_NAME` | backend | Phase 1+ | Default suggestion: `accessibility_auditor` |
| `AI_PROVIDER` | backend | Phase 4+ | Must be exactly `gemini` or `openrouter`; raises a config error on import if missing or unrecognized — never defaults silently |
| `GEMINI_API_KEY` | backend | Phase 4–5 (if `AI_PROVIDER=gemini`) | Free tier via Google AI Studio (aistudio.google.com/app/apikey); no credit card required |
| `OPENROUTER_API_KEY` | backend | Phase 4–5 (if `AI_PROVIDER=openrouter`) | Free models (`:free`-suffixed slugs) via openrouter.ai/keys; no credit card required |
| `OPENROUTER_MODEL` | backend | Phase 4–5 (if `AI_PROVIDER=openrouter`) | A current vision-capable `:free` slug confirmed at openrouter.ai/models before being written here |
| `MAX_IMAGES_PER_SCAN` | backend | Phase 4+ | Cost-control cap, user-approved value |
| `SCANNER_SERVICE_URL` | backend | Phase 7+ | Points at the scanner's local or deployed URL |
| `CORS_ALLOWED_ORIGINS` | backend | Phase 7+ | Comma-separated; must include the live frontend domain in production |
| `BACKEND_PORT` | backend | Phase 7+ | Default `8000` |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | Phase 8+ | Points at the backend's local or deployed URL |

No variable in this table is ever assigned a real value inside a tracked file. `.env.example` carries names only.

## Appendix B — Common Cross-Phase Issues

| Issue | Where it bites | Fix |
|---|---|---|
| CORS misconfiguration | Phases 7, 8, 10 | Origin list must be updated every time a new frontend domain (local, preview, production) comes into existence |
| MongoDB connection drops under load | Phases 1, 7 | Confirm connection pooling settings on the Motor client; check Atlas connection limits on the free tier |
| AI API cost runaway | Phases 4, 5, 7 | The per-scan image cap and orchestration-layer concurrency limit are the two real controls — both must be enforced, not just one |
| Secret leakage into git history | All phases | Run the Phase 10 secret-scan command periodically, not just once before the first deploy |

## Appendix C — Definition of Done (Whole Project)

- [ ] A user can paste a real public URL and get a violation report with AI-generated fixes in well under 15 seconds (or the agent has explicitly flagged to the user where reality diverges from this target and why)
- [ ] Every fix is shown as a real before/after diff — no black-box "fixed" badge anywhere in the UI
- [ ] No login is required for a single scan
- [ ] Contrast fixes are deterministic and self-verified; alt-text and ARIA fixes are AI-generated, grounded, and degrade to "needs manual review" rather than fabricating a result
- [ ] All three services are live (Vercel frontend, Render backend, Render scanner) and have been smoke-tested against real public URLs in production
- [ ] `docs/benchmarks.md` contains real, reproducible numbers for N ≥ 5 real sites, including a manually-reviewed accuracy percentage
- [ ] No secret has ever been committed to the repository
- [ ] `docs/guide.md`, `README.md`, and `CHANGELOG.md` accurately reflect the as-built system
