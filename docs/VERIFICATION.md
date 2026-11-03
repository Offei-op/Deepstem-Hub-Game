# Verification record

## October 31 automatic host restart

`Start Studio.cmd --no-browser` was invoked twice consecutively against an already-running local studio. Both runs identified and stopped the three existing hosts and old launcher supervisor, then brought API/preview/frontend back on ports 8000/8001/5173 with new process identities. Team, game-version, generation and submission counts, event/timer configuration, `.env`, and private provider settings matched their pre-restart fingerprints. No AI generation was issued by the verification.

The backend suite passes **59 tests, with 1 paid probe skipped**. Twelve focused launcher tests cover checkout ownership, unrelated or inaccessible processes, unknown port owners, foreign launcher scripts, preflight before any stop, active-generation refusal, the atomic SQLite shutdown guard, missing database refusal, crashed API recovery, browser-window preservation, supervisor shutdown order, and the concurrent-start lock. The helper uses cached process identities rather than terminating whatever happens to reuse a PID. No frontend code was changed for this update.

## October 31 usability update

The current update passes **44 backend tests (1 paid probe skipped)**, **9 frontend tests**, **3 Chrome end-to-end tests**, and the production build. See `UX_REVIEW.md` for the layout decisions and screenshot measurements at 1366×768 and 1920×1080. The laptop Generate button is fully inside the first viewport without reducing the 17 px prompt/button type. Screenshots are saved under `artifacts/ux-overhaul/`.

The existing virtual environment had been recreated with Python 3.13 while retaining Python 3.12 binary packages. Dependencies were reinstalled for 3.13, and the launcher now checks/repairs import failures. The actual local launcher was run successfully: API on 8000, isolated preview on 8001, frontend on 5173. Existing data/configuration was preserved; no active generation was present at restart. Organizer local-link behavior and private, authenticated provider configuration are covered by tests; provider saving was exercised through the browser with dummy keys and no paid call. Tests run on separate ports so the normal app can remain available.

The earlier implementation verification is retained below as history; Docker/public HTTPS and real-provider calls remain unverified.

This file records performed checks, separate from deployment instructions. Last updated for the October 30, 2026 implementation in this workspace.

Verified:

- Python 3.12 virtual environment with installed official `openai` 2.54.0 and `google-genai` 2.34.0. SDK interface/configuration checks use no network calls.
- Backend mocked test suite: **40 passed, 1 skipped** (the gated paid probe). Includes 10 simultaneous teams, independent database-service reservation contention, spending/quota limits, idempotency, both-provider failure, bounded retries, billing-error classification, uncertain usage, version restore, submission deadlines, session/token expiry, isolation and HTML/JavaScript validation.
- Frontend Vitest: **7 passed**. TypeScript and Vite production build completed successfully (251 KB main JavaScript before gzip).
- npm dependency audit after patched tooling installation: zero vulnerabilities reported.
- Five checked-in standalone starters pass structural/capability validation. Static JavaScript syntax checking uses Tree-sitter without executing scripts in Python.
- Real-Chrome Playwright browser suite: **2 passed**. Exercised organizer/team login, generation, modification, restore, standalone download and offline playback, final submission, mobile overflow, deadline locking, judging gallery and all five starter keyboard/restart smoke checks. Browser checks confirmed parent DOM, storage and cookie access denial and fetch blocking under preview CSP. Screenshots and the exported HTML are in ignored `artifacts/`.
- Standalone HTTP load rehearsal against a running mock-only Uvicorn API: **10 of 10 simultaneous teams passed**, each with one saved version/used allowance and no residual reservations. Observed completion/poll times were 0.36–1.33 seconds in this local mock rehearsal; these are **not real-provider latency measurements**.
- `pip check`: no broken requirements. The sample environment loads blank provider prices as unconfigured rather than failing startup.

Not verified by those checks:

- Paid provider access, actual generation quality, real provider latency/rate limits or billing. The opt-in paid test remains skipped unless expressly enabled.
- Docker image build/Compose startup. Docker is not installed in this execution environment.
- Public HTTPS hosting, target reverse-proxy headers, DNS, campus Wi-Fi, container volume ownership/read-only WAL behavior on the actual host or backup/restore on that host.
- Full human playthroughs, accessibility audit, browser security against every obfuscated program, or all keyboard/laptop combinations.

Before declaring the live event deployment ready, perform the target-host and human checks in `EVENT_DAY.md`, inspect `SECURITY.md`, rehearse a small paid generation/modification with the selected models, and compare the spending ledger with provider reports.
