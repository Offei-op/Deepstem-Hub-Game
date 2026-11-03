# Style references and event archives

## Teams: up to three style images

In **Your AI co-creator → Guide the visual style**, choose screenshots or artwork, then describe the game or change and generate as usual. Images stay saved for the team's future edits. Remove an image to replace it; a team can have at most three active images. Adding/removing images does not use a generation allowance. References cannot change during an active request or after building ends.

The browser accepts still JPEG, PNG and WebP files up to 5 MB and 16 megapixels and scales them before upload. The backend independently decodes, validates and re-encodes uploads as metadata-free JPEG, with a 768-pixel longest side. It enforces input byte/pixel limits and at most three images atomically. Raw filenames are never filesystem paths. Images are authenticated same-origin resources, never public asset URLs or preview-origin files. Team ownership, CSRF and event scope are checked server-side. Removed references used in earlier requests remain private historical evidence; each team has a 100-image lifetime safety cap per event.

Images go to the configured AI provider only when generating, including provider fallback where configured. OpenAI receives structured `input_image` parts with low detail; Gemini receives inline image bytes through the official SDK. Neither adapter uses image-generation APIs. References guide procedural canvas artwork; they are not embedded as copied image assets in exported games. Text or instructions inside images are untrusted creative material. Choose a model that supports image inputs and structured game-code output. Practice mode still returns the deterministic starter; it does not claim to apply the images.

Image input tokens are included in provider-reported input usage. Before any paid call, the input bound includes a configurable allocation per reference (`REFERENCE_IMAGE_TOKEN_RESERVE`, default 6000). It shares the event's maximum input-token limit. The existing maximum input/output reservation, combined fallback/retry reservation, actual usage ledger and event ceiling remain enforced. This allocation is deliberately conservative for resized low-detail style references; rehearse and adjust it for the actual configured model. It is not a universal tokenizer guarantee. Provider-side spending limits remain essential. No extra fixed image-generation price is charged by this feature.

## Organizers: New event

Open **New event** in the organizer header. Enter a name, theme, duration, event ceiling and team allowances, then type **NEW EVENT** to confirm. Creation is blocked while any generation or team request remains active. The current event moves to **Event archive** and the new event starts in ready state, unfrozen, with emergency mode and generation pause cleared. Existing AI keys/models/pricing and permanent website addresses remain configured.

Teams must receive new access codes. Previous team sessions and codes cannot access the new event. Team names can be reused, but team and version IDs are preserved rather than recycled. A repeated or concurrent creation request cannot archive the new event accidentally: it must identify the expected current event.

The archive retains games, versions, submissions, prompts, reference evidence and usage in the database. Organizers can inspect all saved game versions, play them through the existing isolated preview service, download standalone HTML and export the event record including reference images and usage. Archived events are read-only; old teams cannot keep editing. The active dashboard and spending ceiling include only the current event. Starting a new event does not erase previous provider charges or reset provider billing limits.

## Resetting the existing clock

**Event settings → Reset competition clock** now has **Also reopen AI generation and submissions**. Leave it unchecked to reset only the timer, or select it to clear submission freeze, AI pause and emergency mode. Reset preserves the current teams, games and usage. **New event** creates a separate competition with an archive and fresh team allowances instead.

## Upgrading and rollback

Version 2 adds event scope to teams, archived event metadata, private style references and reference IDs on generation records. An explicit atomic SQLite v1→v2 migration preserves historical IDs/content and changes the team-name constraint to uniqueness within each event. Run one API worker. Stop application services, create a consistent SQLite backup (including WAL content using SQLite's backup API), back up private configuration and source, then install requirements and start the upgraded application. Initializing again is safe.

For rollback, stop all API and preview processes first. Preserve the upgraded database separately, restore the matching **pre-upgrade database and source together**, and restore provider/tunnel settings only if they changed. Do not run old code against schema v2 or discard a database containing new participant work. Never delete WAL/SHM files while database processes are running. The domain/DNS configuration does not need to change during an application update.

Automated checks use mock providers. Real model image understanding and visual quality still require a deliberately authorized paid rehearsal; the automated suite never performs it by default.
