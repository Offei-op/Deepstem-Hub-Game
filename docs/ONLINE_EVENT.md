# Laptop hosting with public HTTPS access

Open **Start Event Online.cmd**. It builds the website and publishes separate app and preview origins. After permanent setup it uses your named tunnel and keeps the same addresses on restart. Without permanent setup it allocates two temporary rehearsal links. Existing hosts are replaced only after configuration validation/build and a check that no generation is running. Your teams, games, submissions and private provider settings remain saved. Startup makes no AI request.

## Permanent addresses on your own domain (recommended)

1. Buy a domain and activate it in Cloudflare by changing its nameservers at the registrar. This project uses `deepstemhubgame.online`.
2. Open **Set Up Permanent Hosting.cmd** once. Sign in to the Cloudflare browser tab, select your domain, and click **Authorize**. This creates a private management certificate in your Windows user's `.cloudflared` folder. Setup creates one named tunnel and two DNS records, without replacing conflicting records.
3. Open **Start Event Online.cmd**. Wait for **ONLINE STUDIO IS READY**. Contestants use **https://studio.deepstemhubgame.online**; generated games use **https://games.deepstemhubgame.online**. Both addresses use the same tunnel, with independent hostname routes and a reject-by-default catch-all. Teams only need the studio link and their access code.
4. The launcher opens the private organizer access file. Reopening it after a restart gives you the current organizer sign-in button. The public domain remains the same; the private organizer password changes each hosting session.

For another domain, run `.venv\Scripts\python.exe scripts\permanent_network.py --domain your-domain.example` from the project folder. Do not run setup concurrently with startup. Setup is repeatable: it reuses the saved tunnel credential and does not create duplicate tunnels. If one DNS route fails, resolve the conflict in Cloudflare and repeat setup; existing records are not overwritten.

Keep `data-private/tunnel-credentials.json` secret: it permits operating this tunnel. `data-private/permanent-hosting.json` stores its ID and hostnames. Both are excluded from Git and served files. The broader management certificate is used only during setup; the running connector receives the tunnel credential, never provider/API credentials. Back up these files securely with the existing database and provider settings. Do not share private backups or the organizer access file.

Your laptop must stay plugged in, awake, connected to reliable internet, and running the online launcher. There is no router port forwarding and no need to expose local ports to the network. This setup does not install an automatic Windows service or change sleep settings. If connectivity drops, the connector attempts to reconnect using the same addresses; the launcher flags unreachable public routes. A permanent hostname removes disposable-link changes, but does not provide an uptime guarantee.

Cloudflare Tunnel (`cloudflared`) must be installed and a real AI provider must already be configured through the organizer screen. Strong independent session/preview secrets are required. Invalid permanent settings stop startup rather than silently creating temporary links. If temporary tunnel allocation fails, the existing local studio is left running. A provider key can be present but invalid; check an actual generation separately before the event.

## Joining and organizer access

- The launcher prints the contestant URL. Share that URL and each team's private access code.
- The launcher opens `data-private/online-access.html`. Its organizer button signs you in using a random password for this online session. The password fragment is removed before login and is never sent as part of a page URL to the server.
- Keep the private access file and organizer button confidential. The manual online password is also in that file. The ordinary local password and `.env` are not changed.
- Public, non-secret status/URLs are in `artifacts/online-status.json`. Private tunnel/service logs are under `data-private/online-*.log`.
- **Stop Event Online.cmd** stops this checkout's online services, including orphaned tunnels, and replaces stale organizer links with a stopped notice. It refuses to interrupt active generations. **Start Studio.cmd** reuses a healthy online session instead of disconnecting it. To explicitly return to local-only use, run `Start Studio.cmd --local`.

## Isolation boundary

The public app is the built Vite output, served with the API by one FastAPI worker on loopback port 8080. Source files, `.env`, private configuration and Vite's development server are not published. The app accepts its configured hostname and loopback health checks only. HTTPS sessions use Secure, HttpOnly, host-only cookies and existing CSRF/team authorization checks.

The separate preview process listens only on loopback port 8081 and receives an explicit environment allowlist with no provider keys, organizer password or app session secret. Its settings do not load `.env`. Its tunnel gets a different hostname. Preview remains cookieless, capability-signed, sandboxed without same-origin permission, and protected by the existing network-blocking CSP. The app's frame policy permits only that exact preview origin. No router port forwarding or inbound Windows firewall exception is required.

Two temporary hosts may share the provider's registrable domain; separate registered sites remain preferable for browser process isolation. Browser sandbox/CSP cannot completely prevent CPU abuse by generated JavaScript. The preview process shares the OS user and can read the database file; this is not container/OS sandbox isolation.

## Before the event

Keep the laptop plugged in, awake, and on reliable internet. Open the contestant link on a phone using mobile data, then rehearse with team laptops. Check login, an existing preview, keyboard controls, download, and a small real AI generation when ready. Keep exported games and database backups.

Cloudflare Quick Tunnels (used only without permanent setup) are **for rehearsal/development**, have no uptime guarantee, allow at most 200 concurrent in-flight requests per tunnel, and change hostnames on restart. Existing teams/games persist, but distribute the new link after restarting. Stopping either the laptop or tunnel stops public access. Use the permanent setup above for stable addresses.

Official reference: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

## Verification performed on this laptop — 31 October 2026

Permanent domain verification was also completed on **1 November 2026**: `studio.deepstemhubgame.online` and `games.deepstemhubgame.online` resolved publicly, the named tunnel connected, and `npm run check:online` passed public entry, private organizer sign-in, Secure/HttpOnly cookies, preview API denial and saved-game isolation. No paid AI request was made. The named connector uses automatic transport selection; health requests identify themselves as `DeepstemStudio/1.0` because the default Python client signature was rejected by Cloudflare with error 1010. The bare root domain is not configured as a studio route; use the `studio.` address.

Production build completed; 64 backend tests passed (one paid integration probe skipped), and 10 frontend tests passed. The actual public HTTPS URLs were opened in Edge: contestant login page, private organizer sign-in, Secure/HttpOnly/SameSite cookies, and an existing saved game were verified. The game could not access parent DOM, browser storage or cookies; app session cookies were absent from preview requests, and preview rejected application API routes. No paid AI request was made. Run `npm run check:online` from `frontend` to repeat the read-only browser check while online access is running.

The initial free-link allocation encountered intermittent provider timeouts. The launcher now retries each allocation at most three times and leaves local services running if link allocation fails. Public availability still depends on your connection and Cloudflare; a separate-device/campus-network rehearsal and real provider generation remain event-day checks.
