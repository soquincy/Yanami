# Features

## Persona

* **Structured Personality Editor** — `/setpersona core` and `/setpersona style` open separate modals for personality, background, beliefs, language style, and system instructions.
* **Persona Profiles** — save, load, list, and delete named presets with `/personasave`, `/personaload`, `/personalist`, `/personadelete`.
* **Persona Lock** — prevent accidental overwrites with `/personalock` and `/personaunlock`.

## Memory

* **Short-Term Conversation Memory** — rolling per-channel context window with automatic summarization. Cleared with `/clearmemory`.
* **Long-Term User Memory** — facts extracted from conversation, scored by importance (0.0–1.0), and persisted to `memory.json` keyed by `guild_id:user_id`. Each fact stores content, importance, timestamp, message ID, and channel ID. Injected into the system prompt automatically on future interactions. Capped at 20 facts per user; low-importance facts pruned automatically.

## Autonomy

* **Intent-Based Autonomous Mode** — scores each message using a heuristic pipeline: direct mention/reply (+0.90), attachment present (+0.50), code block (+0.40), semantic trigger words (+0.40), question mark (+0.20), channel memory (+0.10), with penalties for filler messages (-0.30) and monologues (-0.20). Fires only when confidence clears the configured threshold.
* **Configurable Threshold** — `low` = 0.70, `default` = 0.50, `high` = 0.35.
* **Cooldowns** — 120-second per-channel and 60-second per-user cooldowns prevent over-engagement.

## Input Handling

* **Multimodal Input** — images, PDFs, audio, video, and code files all processed through Gemini's multimodal pipeline. All Discord-deliverable Gemini MIME types supported.
* **Debounced Responses** — per-user debounce collapses rapid successive messages into one response.
* **Injection Detection** — prompt injection attempts caught and neutralized before reaching the model.

## AI Commands

* **AI Write** (`~write`) — structured output using the active persona.
* **AI Ask** (`~ask`) — conversational response using the active persona.
* **Web Search** (`~search`) — live results summarized with AI. Requires Google Search API.
* **Embed Footers** — all AI command embeds show requester name and truncated prompt in the footer.

## Utilities

* **Audio Separation** (`~separate`) — isolates vocals and instrumental via MVSEP (BS Roformer).
* **Math Engine** (`~math`) — solves equations via Wolfram|Alpha hybrid API.
* **Media Downloader** (`~download`, `~audio`) — downloads video or MP3 directly in chat (10 MB limit).
* **Persistent Prefix** (`~prefix`) — changes the command prefix and saves it across restarts.
* **Hybrid Commands** — every command works as both a prefix command and a slash command.
* **No DM AI** — AI commands are server-only by design.
* **Debug Tools** — `/debugpersona` shows active persona, last prompt, model, lock state, and autonomy status.
