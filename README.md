# Freesona - The Discord Bot You Customize

[Discord Support](https://discord.gg/fEHw2e2zrW)

Freesona is a flexible Discord bot that lets you live-edit its personality and configuration directly from Discord. Powered by Gemini AI and integrated with web search, math, and media tools, it’s a versatile companion for any server.

## Features

* **Dynamic Persona:** Use `/setpersona` to change how the bot thinks, speaks, and acts via a private Discord modal.
* **Persistent Prefix:** Use `~prefix <symbol>` to instantly change the bot’s prefix. This change is saved to a JSON file and persists across restarts.
* **AI Chat:** Use `~write` or `/write` to chat with the bot using the active persona.
* **Web Search:** Use `~search <query>` to get an AI-summarized overview from the live web.
* **Math Engine:** Solve equations using the Wolfram|Alpha hybrid API.
* **Media Downloader:** Download videos or convert links to MP3 directly in chat (10 MB limit).
* **Hybrid Commands:** Supports both traditional prefix commands and slash commands (`/`).

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
| **Windows (Local)** | `persona.txt`                 | Saves the file in the bot’s project folder    |
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