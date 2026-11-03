# Readability and setup overhaul — October 31, 2026

The studio uses one shared design system in `frontend/src/design-system.css`. Main body text is 16 px on laptops and 17 px on wide desktops; supporting text is 14–16 px; prompt text is 17–18 px; the main action is 17 px; panel headings are 23–25 px. Only incidental branding metadata falls below 13 px. Form placeholders, hints and descriptions use lighter colors against distinct dark surfaces. Focus rings are visible, form labels are associated, dialogs have accessible names, and interactive targets are at least 44 px high.

The composer comes before conversation history. Its editable area is 176 px tall at 1366×768 and 220 px at 1920×1080 and can be resized. History uses ordinary page flow. The desktop split gives the editor a practical width alongside a larger playable preview. Supporting history/submission controls sit below the preview, and the layout becomes one column on narrower screens. Navigation becomes horizontal on phones. Preview controls include text labels. Success feedback uses a temporary toast rather than pushing the editor down the page.

Organizer setup puts Connect AI, team invitations and theme/clock controls first. Metrics follow event controls; provider attempt logs remain expandable. The AI connection dialog keeps its title, close and Save action visible while its fields scroll. Credentials are stored privately by the server, never echoed back or exposed to preview.

`Start Studio.cmd` or `python scripts/launch.py` starts all three services together. It repairs missing/incompatible Python dependencies, creates local settings only when absent, preserves existing configuration/data, and prepares one-use local organizer access. First-run installation requires internet and Python/Node already installed. Production still uses password authentication and the documented HTTPS/isolation deployment.

## Actual visual QA

Playwright captured and visually inspected these views at **1366×768** and **1920×1080**, at **100% browser zoom** (device pixel ratio 1):

- Team and organizer sign-in
- Empty creation workspace
- Workspace with a generated game
- Organizer dashboard
- Connect AI dialog

Images are in `artifacts/ux-overhaul/`. `measurements.json` records actual computed sizes and bounds. At 1366×768, the main Generate button ends at approximately y=748, fully inside the initial 768 px view; the page continues naturally for secondary actions. There is no horizontal page overflow at either requested desktop size. The existing phone-sized workflow also checks overflow and visible game status.

The first screenshot pass showed the Generate action below the laptop viewport and the connection form’s Save action off screen. The second pass reduced decorative space and added a persistent dialog footer while preserving the reading sizes. Those changes were rechecked through screenshots and automated bounds assertions.

Verification: **44 backend tests passed, 1 paid test skipped; 9 frontend tests passed; 3 Chrome browser tests passed**, including the complete create/edit/restore/export/submit/freeze workflow, five starter keyboard/restart checks, and provider setup with dummy credentials and no paid generation. Production build passes. The one-use organizer link is also tested for expiry, repeat-use rejection, StrictMode double invocation, and use in an already-open sign-in page. Docker/public HTTPS and live-provider calls remain outside this local verification.
