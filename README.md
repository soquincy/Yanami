# Freesona - The Discord Bot You Customize

[Discord Support](https://discord.gg/fEHw2e2zrW)

Most AI Discord bots are wrappers with a paywall in front of them. You get a personality someone else chose, running on infrastructure you don't control, locked behind a subscription you didn't ask for.

Freesona is different. It's a self-hosted bot template where **you write the system prompt** — live, from Discord, without touching code. Fork it, drop in your API key, write a persona, and your bot becomes whatever you need it to be: a server mascot, a character, a focused assistant, or nothing AI-related at all if you'd rather just use the utilities. Every part of it is open, modular, and yours.

No credits. No voting. No "upgrade to unlock." Just a bot that does what you tell it.

## What makes it worth forking

**`/setpersona` is the whole point.** It opens a private modal where you write a plain-text system prompt — the bot's personality, rules, tone, and behavior — and it takes effect immediately. No restart. No config file edit. No dashboard. You can make it a customer support agent, a lore character for a roleplay server, or a straight-talking utility bot with no personality at all. The choice is entirely yours.

Everything else — web search, math, media downloads, moderation — is there because a useful bot needs more than one trick. But the persona system is what separates Freesona from a generic AI wrapper.

**It's also built to be read.** The codebase is fully modular using discord.py cogs. Each feature lives in its own file. If you want to strip out the AI entirely, delete `cogs/genai.py` and remove one line from `main.py`. If you want to add something new, you don't have to touch anything that already works. That's intentional.

## Features

* **Dynamic Persona:** `/setpersona` opens a private modal to rewrite the bot's system prompt live. No restart required.
* **AI Chat:** `~write` or `/write` queries the bot using whatever persona is active.
* **Web Search:** `~search <query>` pulls live results and summarizes them with AI.
* **Math Engine:** Solves equations via the Wolfram|Alpha hybrid API.
* **Media Downloader:** Downloads video or converts to MP3 directly in chat (10 MB limit).
* **Persistent Prefix:** `~prefix <symbol>` changes the command prefix and saves it across restarts.
* **Hybrid Commands:** Every command works as both a prefix command and a slash command.

---

## Getting Started

### 1. Installation

```bash
git clone https://github.com/soquincy/Freesona.git
cd Freesona
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory. Configure file paths based on your hosting environment to ensure data persistence:

| Variable           | Recommended Value (Cloud)  | Description                             |
| :----------------- | :------------------------- | :-------------------------------------- |
| `AI_PERSONA_FILE`  | `/etc/secrets/persona.txt` | Path to the AI personality instructions |
| `CONFIG_FILE_PATH` | `/etc/secrets/config.json` | Path where the custom prefix is stored  |

**Example `.env`:**

```dotenv
BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
CHANNEL_ID=YOUR_LOG_CHANNEL_ID
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
GOOGLE_SEARCH_API_KEY=YOUR_GOOGLE_SEARCH_API_KEY
SEARCH_ENGINE_ID=YOUR_GOOGLE_SEARCH_ENGINE_ID
WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT
WOLFRAM_APPID_LLM=YOUR_WOLFRAM_APPID_LLM
AI_PERSONA_FILE=/etc/secrets/persona.txt
CONFIG_FILE_PATH=/etc/secrets/config.json
BOT_NAME=Freesona
```

### Persona File Paths

| Environment         | Recommended `AI_PERSONA_FILE` | Description                                   |
| :------------------ | :---------------------------- | :-------------------------------------------- |
| **Windows (Local)** | `persona.txt`                 | Saves the file in the bot's project folder    |
| **Railway (Cloud)** | `/etc/secrets/persona.txt`    | Saves to a persistent volume (requires mount) |
| **Linux (Server)**  | `./persona.txt`               | Uses a relative path in the current directory |

---

## Persistence & Storage

The bot uses the `/etc/secrets` directory (or your local root) to manage data.

* **Prefix Management:** On startup, the bot reads `config.json`. If you use the `~prefix` command, the bot overwrites this file to ensure your choice remains active after a reboot.
* **Persona Storage:** The `/setpersona` command writes directly to `persona.txt`. The bot reloads this file for every AI interaction.
* **Cloud Hosting (Railway/Render):** You must mount a **volume** to `/etc/secrets`. For Render, create `persona.txt` in the environment page. Without a volume, any changes made via commands will be lost when the bot redeploys.

---

## Admin Commands

| Command            | Action                                         | Permissions     |
| :----------------- | :--------------------------------------------- | :-------------- |
| `/setpersona`      | Opens a modal to edit AI behavior              | Bot Owner       |
| `~prefix [symbol]` | Changes the command prefix (e.g., `~prefix !`) | Administrator   |
| `~purge [limit]`   | Deletes a specified number of messages         | Manage Messages |

---

## Acknowledgements

* [discord.py](https://discordpy.readthedocs.io/)
* [Google Gemini](https://ai.google.dev/)
* [Wolfram|Alpha](https://developer.wolframalpha.com/)
* [yt-dlp](https://github.com/yt-dlp/yt-dlp)

---

## License

Licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
