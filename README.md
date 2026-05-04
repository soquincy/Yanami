# Freesona - The Discord Bot You Customize

[Discord Support](https://discord.gg/fEHw2e2zrW)

Most AI Discord bots are wrappers with a paywall in front of them.You get a personality someone else chose, running on infrastructure you don't control, locked behind a subscription you didn't ask for.

Freesona is different. It's a self-hosted bot template where **you write the system prompt** — live, from Discord, without touching code. Fork it, drop in your API key, write a persona, and your bot becomes whatever you need it to be: a server mascot, a character, a focused assistant, or nothing AI-related at all if you'd rather just use the utilities. Every part of it is open, modular, and yours.

No credits. No voting. No "upgrade to unlock." Just a bot that does what you tell it.

## What makes it worth forking

**`/setpersona` is the whole point.** It opens a private modal where you write a plain-text system prompt — the bot's personality, rules, tone, and behavior — and it takes effect immediately. No restart. No config file edit. No dashboard. You can make it a customer support agent, a lore character for a roleplay server, or a straight-talking utility bot with no personality at all. The choice is entirely yours.

Everything else — web search, math, media downloads, moderation — is there because a useful bot needs more than one trick. But the persona system is what separates Freesona from a generic AI wrapper.

**It's also built to be read.** The codebase is fully modular using discord.py cogs. Each feature lives in its own file. If you want to strip out the AI entirely, delete `cogs/genai.py` and remove one line from `main.py`. If you want to add something new, you don't have to touch anything that already works. That's intentional.

## Features

* **Dynamic Persona:** `/setpersona` opens a private modal to rewrite the bot's system prompt live. No restart required.
* **Persona Profiles:** Save, load, and list named persona presets with `/personasave`, `/personaload`, and `/personalist`.
* **Persona Lock:** Prevent accidental overwrites with `/personalock` and `/personaunlock`.
* **AI Write:** `~write` generates structured, formatted output using the active persona.
* **AI Ask:** `~ask` answers questions conversationally using the active persona.
* **Conversation Channel:** Designate a channel where the bot joins the conversation — responds only when mentioned or replied to, with short-term memory per channel.
* **Web Search:** `~search <query>` pulls live results and summarizes them with AI.
* **Math Engine:** Solves equations via the Wolfram|Alpha hybrid API.
* **Media Downloader:** Downloads video or converts to MP3 directly in chat (10 MB limit).
* **Persistent Prefix:** `~prefix <symbol>` changes the command prefix and saves it across restarts.
* **Hybrid Commands:** Every command works as both a prefix command and a slash command.
* **No DM AI:** AI commands are server-only by design.

---

## Getting Started

### 1. Installation

```bash
git clone https://github.com/soquincy/Freesona.git
cd Freesona
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory:

```dotenv
BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
CHANNEL_ID=YOUR_LOG_CHANNEL_ID
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
GOOGLE_SEARCH_API_KEY=YOUR_GOOGLE_SEARCH_API_KEY
SEARCH_ENGINE_ID=YOUR_GOOGLE_SEARCH_ENGINE_ID
WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT
WOLFRAM_APPID_LLM=YOUR_WOLFRAM_APPID_LLM
BOT_NAME=Freesona

# Local (self-hosted)
AI_PERSONA_FILE=persona.txt
AI_PERSONAS_FILE=personas.json
CONFIG_FILE_PATH=config.json

# Cloud (Railway/Render — requires /etc/secrets volume mount)
# AI_PERSONA_FILE=/etc/secrets/persona.txt
# AI_PERSONAS_FILE=/etc/secrets/personas.json
# CONFIG_FILE_PATH=/etc/secrets/config.json
```

### 3. File Path Reference

| Environment | Path prefix | Notes |
| :--- | :--- | :--- |
| **Windows / Linux (local)** | `./` | Files saved in project folder |
| **Railway** | `/etc/secrets/` | Requires volume mounted to `/etc/secrets` |
| **Render** | `/etc/secrets/` | Create files manually in environment page |

Without a volume on cloud hosts, any changes made via commands will not survive a redeploy.

---

## Persistence & Storage

* **Prefix:** Read from `config.json` on startup. Overwritten on `~prefix` change.
* **Persona:** Read from `persona.txt` on startup. Overwritten on `/setpersona` submit.
* **Persona Profiles:** Stored as `personas.json`. Survives restarts if path is persistent.
* **Conversation Channel:** Stored in `config.json` as `chat_channel_id`. Set via `/setchannel`.
* **Conversation Memory:** In-memory only (ephemeral). Cleared on restart or via `/clearmemory`.

---

## Command Reference

### AI Commands

| Command | Action | Notes |
| :--- | :--- | :--- |
| `~write <prompt>` | Generate structured written output | Stateless |
| `~ask <question>` | Ask a conversational question | Stateless |
| `~search <query>` | Web search with AI summary | Requires Google Search API |

### Conversation Channel

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/setchannel #channel` | Set the AI conversation channel | Administrator |
| `/clearchannel` | Remove the conversation channel | Administrator |
| `/clearmemory` | Wipe channel memory and summary | Administrator |

The bot only responds in the conversation channel when **mentioned** or **replied to**. It keeps the last 5 messages as context and summarizes older history automatically.

### Persona Management

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/setpersona` | Open modal to edit active persona | Bot Owner |
| `/personalock` | Lock persona against changes | Bot Owner |
| `/personaunlock` | Unlock persona | Bot Owner |
| `/personasave <name>` | Save current persona as a preset | Bot Owner |
| `/personaload <name>` | Load a saved persona preset | Bot Owner |
| `/personalist` | List all saved presets | Bot Owner |
| `/debugpersona` | Show active persona and last prompt | Bot Owner |

### Moderation & Utility

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `~prefix <symbol>` | Change command prefix | Administrator |
| `~purge <limit>` | Delete messages | Manage Messages |
| `~math <equation>` | Solve an equation | Anyone |
| `~download <url>` | Download video | Anyone |
| `~audio <url>` | Download audio (MP3) | Anyone |

---

## Acknowledgements

* [discord.py](https://discordpy.readthedocs.io/)
* [Google Gemini](https://ai.google.dev/)
* [Wolfram|Alpha](https://developer.wolframalpha.com/)
* [yt-dlp](https://github.com/yt-dlp/yt-dlp)

---

## License

Licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## Roadmap

### Short-term

* Add `personas.json` sample file so forkers have working presets to start from
* Update `persona.txt.sample` with a fully worked example of a good persona prompt
* Audit `requirements.txt` — pin `google-genai`, `aiohttp`, and all dependencies to versions confirmed working on Railway

### Medium-term

* `/personadelete <name>` — profiles can be saved, loaded, and listed but not removed yet
* Username memory persistence — display names are currently in-memory only and lost on restart; a lightweight JSON store in `/etc/secrets` would fix this
* `~ask` command visible in `~help` — currently categorized under AI Persona but missing from Fun & Info where conversational commands live
* `~today` command audit — referenced in the help cog but unconfirmed if implemented

### Long-term

* Multi-model support — swap between Gemini, Gemma, and other providers via an env variable or command without touching code; `MODEL_NAME` is already a single constant so the architecture supports it
* Persona gallery — a collection of ready-made `persona.txt` examples in the wiki or README showing what Freesona can actually do; the fastest way to sell a fork to someone who just landed on the repo
* Web dashboard — a simple FastAPI page for persona editing to lower the barrier for non-technical server owners; `fastapi_server.py` already exists in the repo as a foundation
