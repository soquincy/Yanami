# Freesona - The Discord Bot You Customize

![Freesona Banner](assets/b_freesona.png)

[Discord Support](https://discord.gg/vXPRs2cHSE)

Most AI Discord bots give you a product. Verba, MEE6, and every other hosted platform give you a personality someone else built, running on infrastructure you don't control, with a ceiling you'll eventually hit.

Freesona is different. It's a free, open alternative to hosted persona bots — with no ceiling. Fork it, drop in your API key, and get a self-hosted bot that can be a convincing AI character, a focused server utility, or both. If you want just a fraction of what paid platforms offer and want it completely free, this is for you. If you want to go further and extend it into something no hosted platform can do, you can do that too.

No credits. No voting. No "upgrade to unlock." Just a bot that does what you tell it.

## What makes it worth forking

**The persona system is built to feel alive.** `/setpersona` opens a structured editor — split across modals by category — where you define personality, background, beliefs, communication style, and advanced instructions separately. No single text wall. Changes take effect immediately, no restart required.

**It remembers.** Freesona supports true long-term memory per user, short-term conversation context per channel, and a knowledge base you populate with lore, facts, or whatever context your bot needs. Memory persists across restarts.

**It feels like a person.** Responses can be split into multiple messages with natural delays between them, the way a real person types — not a single block dump.

**It's also built to be extended.** The codebase is fully modular using discord.py cogs. Each feature lives in its own file. Strip out what you don't need, add what you do. Nothing is locked.

## Features

* **Structured Personality Editor:** Define personality, background, beliefs, language style, and system instructions separately via slash command modals.
* **Long-Term Memory:** Automatically remembers important details about users across conversations. Persists to disk.
* **Knowledge Base:** Add, list, and delete knowledge entries your bot references during conversations.
* **Split Messaging:** Responses sent as multiple messages with natural delays — configurable per persona.
* **Autonomous Mode:** Let the bot chime into conversations without being directly mentioned — configurable frequency and cooldown.
* **Persona Profiles:** Save, load, and list named persona presets with `/personasave`, `/personaload`, and `/personalist`.
* **Persona Lock:** Prevent accidental overwrites with `/personalock` and `/personaunlock`.
* **AI Write:** `~write` generates structured, formatted output using the active persona.
* **AI Ask:** `~ask` answers questions conversationally using the active persona.
* **Conversation Channel:** Designate a channel where the bot joins the conversation — responds only when mentioned or replied to, with short-term memory per channel.
* **Web Search:** `~search <query>` pulls live results and summarizes them with AI.
* **Audio Separation:** `~separate` isolates vocals and instrumental from any audio via MVSEP (BS Roformer).
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
MVSEP_API_KEY=YOUR_MVSEP_API_KEY
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
* **Persona:** Assembled at runtime from structured fields stored in `persona.json`. Overwritten on editor submit.
* **Persona Profiles:** Stored as `personas.json`. Survives restarts if path is persistent.
* **Long-Term Memory:** Stored as `memory.json` per user per guild. Persists across restarts.
* **Knowledge Base:** Stored as `knowledge.json`. Persists across restarts.
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
| `~separate <url>` | Separate vocals and instrumental | Requires MVSEP API key |

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
| `/setpersona` | Open structured personality editor | Bot Owner |
| `/personalock` | Lock persona against changes | Bot Owner |
| `/personaunlock` | Unlock persona | Bot Owner |
| `/personasave <name>` | Save current persona as a preset | Bot Owner |
| `/personaload <name>` | Load a saved persona preset | Bot Owner |
| `/personalist` | List all saved presets | Bot Owner |
| `/debugpersona` | Show active persona and last prompt | Bot Owner |

### Memory & Knowledge

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/kbadd <title> <content>` | Add a knowledge base entry | Bot Owner |
| `/kblist` | List all knowledge entries | Bot Owner |
| `/kbdelete <title>` | Delete a knowledge entry | Bot Owner |
| `/memorylist <user>` | View stored memories for a user | Bot Owner |
| `/memoryclear <user>` | Clear memories for a user | Bot Owner |

### Autonomy

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/autonomy on` | Enable autonomous mode | Administrator |
| `/autonomy off` | Disable autonomous mode | Administrator |
| `/autonomy frequency <low/default/high>` | Set how often the bot speaks unprompted | Administrator |

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
* [MVSEP](https://mvsep.com/)

---

## License

Licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## Roadmap

### In progress

* Structured personality editor — modal-based, split by category (personality, background, beliefs, language, system instructions)
* True long-term memory — per-user, per-guild, persisted to disk with auto-extraction and importance scoring
* Split messaging — multi-message responses with configurable delay, toggle per persona
* Knowledge base — persistent entries injected into system prompt context, managed via slash commands
* Autonomous mode — configurable frequency, per-channel cooldown, toggle via command

### Short-term

* `personas.json` sample file with working presets
* `persona.txt.sample` updated with a complete worked example
* `requirements.txt` audit — pin all dependencies to versions confirmed working on Railway
* `/personadelete <name>` — remove saved profiles

### Medium-term

* Username memory persistence across restarts
* Multi-model support — swap providers via env variable without touching code
* Persona gallery in the wiki — ready-made prompts showing what Freesona can do

### Long-term

* Web dashboard via FastAPI for persona editing — `fastapi_server.py` is already in the repo as a foundation
