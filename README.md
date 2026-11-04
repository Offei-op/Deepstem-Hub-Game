# Deepstem Hub AI Game Jam Studio

A small game creation studio for the UMaT, Ghana two-hour AI game jam. React + TypeScript + Vite + Tailwind, FastAPI, SQLAlchemy/SQLite, OpenAI and Google GenAI SDKs. No participant accounts, API keys or development tools required.

Teams enter a code, describe a game, generate, play, ask for changes, revisit versions, download and submit. Organizers control the theme, timer, requests, spending and final entries. The app starts in **clearly labeled mock mode**: prompts choose one of five playable offline games. Mock mode does **not** perform natural-language editing. Configure real providers before the actual event.

## Start here: one-click local studio

On Windows, double-click **`Start Studio.cmd`** in the project folder. It prepares or repairs the Python dependencies, installs frontend dependencies when needed, starts all three services in one window, and opens organizer access automatically. Keep that window open; Ctrl+C stops the services. Python 3.12+ and Node LTS must be installed on the computer.

You do **not** need to edit `.env`, create a password hash, or manage three terminals for local use. The launcher creates private settings on the first run and uses a random, one-use organizer link valid for ten minutes, available only on loopback in development. Existing team data, passwords and configured API keys are preserved. **Opening Start Studio again automatically closes this checkout’s existing API, preview and Vite hosts, then starts a fresh stack.** You do not need to close the old hosts manually. Manual password sign-in remains available; production never enables launcher sign-in.

Automatic restart verifies both the process command and project directory for ports 5173, 8000 and 8001. It leaves unrelated applications and browser windows alone. If another app owns a port, it reports that conflict without stopping any existing hosts. If a generation is running or needs stale-request recovery, restart is blocked until it finishes or is recovered. The SQLite reservation lock prevents another generation starting during shutdown. Repeated double-clicks are serialized during startup. Saved games, codes, sessions, API settings and the competition clock are retained.

In the organizer screen, select **Connect AI**. Paste your organizer API key, enter the model ID and its current input/output prices, then save. It takes effect immediately and makes no paid test call. A blank replacement key keeps the existing key. The screen never returns stored keys. Models and prices remain explicit so spending reservations are conservative. The existing environment variables are still supported for deployment and advanced use.

Provider settings entered in the UI are saved in `data-private/providers.json` locally, or the backend-only `studio-config` Docker volume. They override environment provider credentials/model/prices until changed in the UI or the private file is removed with the server stopped. Back up this private configuration separately and protect it like `.env`; it is never mounted in preview or included in event exports. No restart is needed for UI changes. Connection changes are blocked while generations are running.

To try the participant experience, create a team and click **Open contestant view** in its access-code dialog. The team signs in in a new tab, while the organizer stays signed in at `/admin`. Organizer and team cookies are separate; logging out of one view does not log out the other. Private team join links carry the code in a fragment that is removed immediately on sign-in. The event clock is not started or resumed automatically.

Cross-platform launcher: `python scripts/launch.py` (or the Python executable in `.venv`). First-run dependency installation needs internet access. The three-terminal commands below remain available for development.

## Manual local development (optional)

Requirements: Python 3.12+, Node 22.12+ (or a compatible current LTS), npm. Run commands from the repository root. On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`, and `.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
npm ci --prefix frontend
python scripts/setup_local.py
python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
```

Keep the API terminal open. In two more terminals, activate the same virtual environment and run, from the repository root:

```bash
python -m uvicorn app.preview:create_preview --factory --app-dir backend --host 127.0.0.1 --port 8001 --no-access-log
```

```bash
npm run dev --prefix frontend
```

Open [the studio](http://localhost:5173) or [organizer access](http://localhost:5173/admin). Sign in with the password you chose. Create teams; copy each code while it is visible, share privately, and **Start building**. A team can sign in from another browser context and generate a mock game. The preview uses `127.0.0.1:8001`, a different hostname from the application. Do not open the participant app at `127.0.0.1:5173`.

The database initializes schema version 2 automatically and includes an explicit atomic SQLite migration from version 1. Stop application services and make a SQLite backup before upgrading. Existing IDs, games, submissions and usage are preserved. To initialize explicitly: `python -m app.cli init-db` with `PYTHONPATH=backend`, or run the command from `backend` after setting the correct database URL. `.env` is loaded relative to the process working directory, so running servers from the root is recommended. Event settings persist in the database; environment provider defaults seed the initial event. Organizer-created events retain the configured AI provider selection.

Teams can now save up to **three private style-reference images** beside the prompt composer. Organizers can use **New event** to archive the current competition and create a fresh one, then inspect/download earlier games through **Event archive**. See [Reference images, event archives and safe upgrades](docs/REFERENCE_IMAGES_AND_EVENTS.md) for usage, limits, image-token budgeting and rollback instructions.

## Docker Compose

Requires Docker Engine/Desktop with Compose v2. Containers and deployment have to be verified on your target machine; see `docs/VERIFICATION.md` for checks actually performed in this workspace.

If you already ran `setup_local.py`, use `APP_ORIGIN=http://localhost:8080` for Docker. Compose always overrides `DATABASE_URL` to `/data/studio.db` in both Python services.

Without a Python installation:

```bash
cp .env.example .env
docker compose build
docker compose run --rm --no-deps backend python -m app.cli secrets
docker compose run --rm --no-deps backend python -m app.cli hash-password
```

Put both generated secrets and the Argon2 hash into `.env`. Keep the password hash **single quoted** so Compose does not interpolate its dollar signs. Do not commit `.env`. Then:

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 backend preview frontend
```

Open [the Docker studio](http://localhost:8080/admin). The API is internal to the Compose network, the UI binds to loopback port 8080, and the preview binds to loopback port 8001. SQLite persists in `studio-data`. `docker compose down` keeps it; **`down -v` deletes the event data**.

## Real AI configuration

Check model access and current pricing in your own provider projects. No model identifiers or prices are hardcoded. Use a model supporting structured JSON responses and enough output for an entire HTML game.

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Server-side OpenAI credentials and exact model ID |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Server-side Google GenAI credentials and exact model ID |
| `OPENAI_INPUT_PRICE`, `OPENAI_OUTPUT_PRICE` | USD per **million** input/output tokens for that model |
| `GEMINI_INPUT_PRICE`, `GEMINI_OUTPUT_PRICE` | Same units; account for billed thinking tokens |
| `PRIMARY_AI_PROVIDER` | `openai`, `gemini`, or development-only `mock` |
| `FALLBACK_AI_PROVIDER` | `gemini`, `openai`, or blank to disable |
| `PROVIDER_TIMEOUT_SECONDS` | Per-call deadline, default 600 seconds (10 minutes) |
| `SAFE_RETRIES` | 0–2 retries of explicit rate-limit rejection; default 1 |

Blank pricing values mean **unconfigured**, not free. Both enabled providers must have credentials, a model and nonnegative finite prices before generation. Restart the API after editing secrets, models, prices or timeout limits. Then select the primary and fallback in **Event settings**, save, and test a deliberately small real game. Production refuses mock mode.

Integration was implemented against [official OpenAI structured outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs) (`AsyncOpenAI.responses.parse`, Pydantic, normalized usage, `store=False`) and [official Google GenAI SDK documentation](https://googleapis.github.io/python-genai/) (`Client().aio.models.generate_content`, structured response schema and usage metadata). SDK retries are disabled; the service owns retry and reservation policy. Google’s [Generate Content structured output API](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) remains the API used by this adapter. Model capability/account access must be verified in rehearsal.

## Budget and allowance controls

Initial defaults: maximum 10 teams, 12 released requests + 3 reserved emergency requests per team (15 available after release), 120 minutes, $20 spending ceiling, 10 concurrent team generations. The $10–$20 event target is an organizer planning estimate, **not a fixed price per request**. Defaults for new teams and individual extensions are separate. Failed generations use no team allowance, but their provider costs remain in the ledger.

The database serializes short reservation transactions using `BEGIN IMMEDIATE`. Each request claims a team lock, verifies quota, reserves the maximum possible cost of enabled calls/retries, and enforces the global concurrency limit before any network call. Locks are released after settlement. No database transaction is held during generation. Idempotency keys prevent repeated submissions of the same request from issuing another paid call, even after a browser refresh.

All accounting uses integer micro-USD. For prices in dollars per million tokens, `ceil(input_tokens × input_price + output_tokens × output_price)` is a micro-USD estimate. Reserve uses configured **maximum input/output limits**, both providers and the retry cap, not the student’s optimistic counter. Reservations reduce the displayed available budget immediately. The input guard uses a deliberately conservative UTF-8 byte bound plus schema/instruction overhead; large games may need an increased input limit or a simpler design. Rates, token caps and concurrency should be rehearsed together: if ten maximum reservations exceed your ceiling, lower caps or concurrency rather than assume all calls will be cheap.

Only explicit rate-limit rejections are retried, with capped exponential backoff and jitter. Authentication, billing and invalid model/request errors stop and appear in the attempt ledger. Invalid game output is charged at reported usage and is not automatically regenerated. A timeout, disconnect or 5xx is ambiguous: the full attempt cap remains in estimated spending, the same provider is not retried, and one fallback provider may run within the original combined reservation. There is no intentional overlap between active local calls; a timed-out remote job may still finish at the provider. The event then pauses AI pending cost review. Unknown usage also pauses AI. These are explicit safeguards, not a provider-level exactly-once guarantee.

Check provider reports and use **Reconcile cost** with an evidence note; original attempt estimates remain in exports. Resume AI separately after review. In an abrupt server crash the persistent active request/reservation stays locked, preventing duplicate spending. **Recover stale** becomes available only after the maximum call/retry horizon plus a safety margin; it conservatively charges the held reserve and releases the team. Review provider usage before resuming. Graceful shutdown drains in-process tasks; do not use reload during a live event.

Provider-side controls are mandatory operational setup. Use a dedicated event project/key, least privilege, provider project budgets/usage alerts, rate restrictions and any available hard billing limits/prepaid caps. Verify whether each provider’s “budget” actually blocks requests or merely sends alerts. Set a low provider-side ceiling independently, confirm billing method and quota, and monitor the provider console during the event. Local token prices and reported usage are estimates and cannot bound unknown provider billing changes or unrelated use of the same key.

## Organizer workflow

- Create up to ten teams. Codes are 40 random bits plus a prefix, HMAC hashed at rest with the session secret, and displayed once. Regeneration invalidates all existing team sessions.
- Publish the theme and announcement. Start/pause/resume the server clock. Server time is authoritative; browser countdowns use monotonic elapsed time between refreshes.
- Monitor active teams (heartbeat within five minutes), requests, attempt-level provider/model/tokens/timestamps/duration, cost uncertainty, remaining allowance and in-flight reservations.
- Extend normal allowances or release a team’s reserved emergency requests. Changes never bypass the spending ceiling.
- Pause AI without stopping saved games. Emergency mode pauses AI and publishes an editable participant announcement. Leaving emergency mode does not automatically resume AI or clear the announcement.
- Teams can update their single final submission while building is running. The submission snapshots title, description, team name, final version ID and prompt history. Timer expiry locks generation, restoration, starter/import creation and final edits on the server even if a browser is stale. An in-flight generation may still save a version, but cannot change a frozen submission.
- **End & freeze** ends building and freezes entries. Manual freeze also locks building changes. Resetting the timer or unfreezing is an explicit organizer action; both must be adjusted if intentionally reopening an event.
- The gallery plays entries through the same isolated origin. Inspect any team’s saved versions and download HTML. Export event JSON includes teams (without code hashes), versions, submissions, requests, provider attempts and audit records.

## Production deployment

For public access from your laptop, see [Online laptop hosting](docs/ONLINE_EVENT.md). Run **Set Up Permanent Hosting.cmd** once to connect your Cloudflare domain, then **Start Event Online.cmd** each time you host. It publishes separate studio and game-preview HTTPS origins and keeps organizer access private. Without permanent setup, the online launcher uses temporary rehearsal links.

Use one server with local persistent disk; suggested starting point: 2 vCPU, 2 GB RAM, SSD, stable outbound HTTPS. This is a single-event deployment, not a distributed queue. Run **one API worker**, a separate preview process/container and the built frontend behind a TLS reverse proxy. Do not put SQLite on NFS, share one database across hosts, expose the API container directly, or run Vite on event day.

1. Assign two HTTPS hostnames, preferably on different registrable sites: e.g. `studio.example.edu.gh` and `games.example-games.org`. Point DNS to the server. Install a reverse proxy such as Caddy; adapt `deploy/Caddyfile.example`.
2. Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `APP_ORIGIN=https://studio.example.edu.gh`, `PREVIEW_ORIGIN=https://games.example-games.org`, independent random secrets, an Argon2 organizer hash, real providers, model IDs and verified prices. The server refuses unsafe production defaults.
3. Deploy with Compose. The proxy forwards the application hostname to loopback 8080 and the game hostname to loopback 8001, preserving the original Host header. No app cookies or analytics should ever be configured on the game origin. Do not mount or reverse-proxy `/api` there. Do not add a wildcard CORS policy.
4. Keep the parent app’s CSP `frame-src` restricted to the exact preview origin and the preview’s `frame-ancestors` restricted to the exact application origin. Verify headers after your CDN/proxy. Keep preview access logs off or redact `/play/*` paths (signed links are capabilities). API docs are not intended as a public interactive UI.
5. Keep backend secrets in protected environment files with restrictive OS permissions. Preview gets only its signing secret, origins and read-only SQLite storage. Rotate credentials after the event. Pin tested container digests for the actual rehearsal/release; image tags here are base references.
6. Configure backups and host clock synchronization. Verify HTTPS, cookies, previews, exports, health checks, graceful restart and restoration on the actual host. Run the ten-team rehearsal with real network conditions.

See [security boundaries](docs/SECURITY.md), [event checklist](docs/EVENT_DAY.md), [verification record](docs/VERIFICATION.md).

## Testing

Normal tests never consume API credits:

```bash
python -m pytest backend/tests -q
npm test --prefix frontend
npm run build --prefix frontend
```

Browser tests start isolated API/preview/Vite servers on ports 18000/18001/15173 with a fresh test database under ignored `artifacts/`, so the normal studio can keep running. They force mock mode and a known **test-only** organizer password; never expose these servers to participants.

```bash
cd frontend
npx playwright install chromium
npm run test:browser
```

You can use installed Chrome instead: `PLAYWRIGHT_CHANNEL=chrome npm run test:browser`. On PowerShell: `$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:browser`. `PYTHON_EXECUTABLE` can override the default virtual-environment Python path. Screenshots and an offline export are saved in `artifacts/`. Browser checks exercise the full UI workflow, keyboard input, all starters, cross-origin storage/cookie/parent access denial and CSP network blocking. They are smoke checks, not proof of game quality. Human testers must judge controls, reachable goals, fair collision behavior, restart correctness, performance and fun on student laptops.

The standalone load test creates ten teams against a **fresh rehearsal database** and refuses paid providers by default:

```bash
python scripts/load_test.py --base-url http://localhost:8080
```

It prompts for the organizer password, submits ten requests concurrently, polls completion and verifies saved versions, allowance counts and released reservations. `--allow-paid` is an explicit spending opt-in. Do not run it on the event database.

Optional paid SDK probe (one request, 256 output tokens, configured upper cost guard $0.05; no fallback/retries):

```bash
RUN_PAID_INTEGRATION=YES INTEGRATION_PROVIDER=openai python -m pytest backend/tests/test_paid_integration.py -q
```

PowerShell uses `$env:RUN_PAID_INTEGRATION='YES'` and `$env:INTEGRATION_PROVIDER='openai'`. The probe checks SDK access/structured parsing; it intentionally does not generate a complete game. Follow with one budgeted real-game rehearsal manually. No paid integration results are claimed unless actually run.

## Backup and recovery

Use SQLite’s online backup API, not a plain copy of the live `.db` while WAL writes may be active:

```bash
docker compose exec backend python -m app.cli backup --output /data/backups/event.db
docker compose cp backend:/data/backups/event.db ./event-backup.db
```

For local operation: `python -m app.cli backup --output backups/event.db` with `PYTHONPATH=backend` from the root (PowerShell: `$env:PYTHONPATH='backend'`). Save an organizer JSON export at milestones too. Keep encrypted off-host copies, the exact application release and protected configuration/secrets; do not publish team prompts or codes. Retaining the session secret preserves code hashes; changing it requires reissuing all team codes. Preview secret rotation expires old links immediately.

Restore on a stopped stack. Keep a copy of the old volume first, copy the verified backup to `/data/studio.db` with UID 10001 ownership, and remove stale WAL/SHM files **only while all database processes are stopped**. Start the same application schema version, check health, team login and every submitted game, then reconcile stale requests and provider costs before resuming AI. Test this procedure before event day. Schema v1 is the initial migration; future schema changes need explicit migration code and a pre-migration backup. `create_all` does not migrate existing columns.

## Repository map

```text
backend/app/       API, models, authentication, providers, reservations, preview service
backend/app/starters/   Five checked-in standalone HTML games
backend/tests/     Mocked API/security/concurrency tests and gated paid probe
frontend/src/      Participant studio, organizer dashboard, shared components, styling
frontend/e2e/      Browser workflow and starter smoke tests
scripts/           Starter builder, local setup, ten-team load test, isolated test server
deploy/            Example HTTPS reverse proxy
docs/              Security, contingency, event operations and verification
```

Known limits: natural-language game quality depends on the selected model; validation is structural and capability-oriented, not a proof of playability. Preview isolation relies on current browsers, correct proxy/CSP configuration and a separate cookieless origin; CPU abuse cannot be completely prevented inside a browser iframe. This version has a single administrator password, fixed session expiry, no durable external job runner, a 100-version safety cap per team, a maximum ten teams, JSON exports rather than a reporting warehouse, and no automated future schema migrations. Public internet hosting should receive a deployment-specific security review and rehearsal. This repository does not claim provider billing guarantees or verified production deployment.
