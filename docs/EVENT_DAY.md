# Practical rehearsal and event operations

## At least a day before

- Deploy the exact release on the event host. Verify both HTTPS hostnames from the campus network and actual student laptops. Confirm keyboard focus, full screen, small screens and downloads.
- Create a fresh rehearsal database; run the ten-team load script. Verify ten saved games, one charged allowance per team, no residual active locks and zero mock spend. Inspect provider console rate limits before a separate small paid rehearsal.
- Configure exact provider models/prices and both provider projects’ billing/rate controls. Generate one real game, modify it, restore the first version, download and play without a connection. Rehearse fallback using a deliberately unavailable primary in a **test environment**, not fake success on the production ledger.
- Walk through all five starter games, including win/lose states. Have beginners try a first prompt and one change without coaching. Check laptop performance and fair reachable goals.
- Start/pause/resume/end the timer. Submit, freeze, refresh a stale team browser and verify no further changes are accepted. Test gallery playback and organizer download.
- Take and restore an online SQLite backup onto a rehearsal stack. Check that teams, versions and final entries survive. Practice stale-request recovery and invoice reconciliation after an interrupted test request.
- Keep an offline copy of all starter HTML files, the release, this checklist and a contact sheet. Assign one person to budget/provider monitoring and one to participant help.

## Before participants arrive

- Use a clean event database, not a rehearsal database with consumed quotas. Never delete the only copy of an event.
- Set theme, 120-minute clock, 12 initial requests + 3 emergency requests, team count and budget. Verify configuration persisted after restart. Confirm no pending requests or old submissions.
- Create ten teams of 3–4 students and distribute codes privately. Record codes securely when shown; if lost, regenerate and warn the team it will sign them out. Each team shares one workspace and one concurrent generation.
- Confirm both services and TLS are healthy, disk has space, system time is synchronized, backups work and provider budgets remain available. Open a separate organizer session and gallery.
- Explain: start small, one change at a time, click inside the game for controls, download regularly, submit before time ends. AI-generated code is permitted. Students need no accounts, keys or subscriptions.

## During the two hours

- Start building once everyone can sign in. Use announcements for event-wide help. Watch activity, failures, available budget and in-flight holds.
- Avoid deployments/reloads while requests are running. A repeated browser request with the same key is safe; do not tell teams to repeatedly send new paid prompts.
- Release emergency allowances to teams that need them. Requests do not guarantee equal cost; keep the budget ceiling intact.
- At 30 and 10 minutes remaining, remind teams to download and submit. A successful generation arriving after the deadline cannot replace a locked final entry.
- Back up at milestones. Export the final event JSON before judging. Keep monitoring provider reports even after the app stops issuing requests.

## If a provider fails

1. Check organizer error/attempt status. Rate limits may retry/fall back automatically. Authentication or billing errors need configuration/billing repair; do not silently switch around them. An uncertain cost automatically pauses subsequent AI requests.
2. Turn on Emergency mode and publish a short announcement. Saved games, downloads, starter selection during building and submission of existing games remain usable. The game services do not require a provider to play files.
3. If appropriate, pause the competition clock while organizers investigate. A paused clock disallows building changes/submission updates until resumed. If students should continue with starters, keep the clock running and pause only AI.
4. Review provider usage. Reconcile uncertain calls with an evidence note. Fix credentials, quotas or selected providers, then explicitly resume AI. Exiting Emergency mode alone does not resume it.
5. If the app process restarted mid-call, wait for the stale-recovery safety window, recover the request and reconcile its conservative charge. Never force-release a still-running generation.

## Manual external-tool contingency

Use an organizer-controlled account in [Google AI Studio](https://aistudio.google.com/) or [Bolt](https://bolt.new/) only if available and authorized for the event. Their access, quotas, terms and paid/free availability must be checked in advance; neither is assumed unlimited or free. Do not put the studio’s API keys into participant browsers or external prompts.

Have the team download its current HTML and share the requested change with the assigned organizer. Ask the external tool for **one complete standalone HTML canvas game**, inline CSS/vanilla JavaScript, no external assets/libraries/network/storage/navigation, arrows/WASD, Space and R controls, visible objective and restart. Download the resulting HTML without executing it on the app origin. Under the team inspector, choose **Import a contingency game**, upload the file and validate/save. It uses the same structural rules and creates another immutable version without consuming a studio AI allowance. External charges are outside the app ledger and must be tracked separately against the event’s overall budget.

If validation fails, simplify the generated file or use a bundled starter. Do not relax CSP, grant same-origin access or disable validation to make an external output work. If the platform is completely offline, teams can play already-downloaded HTML and starters locally, and organizers can collect final files on removable storage with team name/title/description and a recorded timestamp. Restore the platform and preserve a clearly documented manual submission record; do not invent a pre-deadline platform submission.

## Closing

- End & freeze, verify every team’s final entry, then open the gallery for judges.
- Download all submitted games and export event data. Take a final database backup and store an encrypted off-host copy.
- Compare ledger estimates with provider reports, including ambiguous calls and external-tool spend. Reconcile with notes.
- Revoke event API keys, expire/reissue access if retaining the site, and follow your student-data retention policy.
