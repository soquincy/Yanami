# Freesona - The Discord Bot You Customize

[Discord Support](https://discord.gg/fEHw2e2zrW)

Freesona is a flexible Discord bot that allows you to live-edit its personality directly from Discord. Powered by Gemini AI and integrated with web search, math, and media tools, it is a versatile companion for any server.

## Features

* **Dynamic Persona:** Use `/setpersona` to change how the bot thinks, speaks, and acts via a private Discord Modal.
* **AI Chat:** Use `~write` or `/write` to chat with the bot using the active persona.
* **Web Search:** Use `~search <query>` to get an AI-summarized overview from the live web.
* **Math Engine:** Solve equations using the Wolfram|Alpha hybrid API.
* **Media Downloader:** Download videos or convert links to MP3 directly in chat (10MB limit).
* **Moderation Suite:** Standard tools including `~purge`, `~ban`, `~kick`, and `~timeout`.
* **Hybrid Commands:** Supports both traditional prefix commands (`~`) and Slash Commands (`/`).

---

## Getting Started

### 1. Installation

```bash
git clone [https://github.com/soquincy/Freesona.git](https://github.com/soquincy/Freesona.git)
cd Freesona
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory. You must configure the `AI_PERSONA_FILE` path based on where you are running the bot:

| Environment | Recommended `AI_PERSONA_FILE` | Description |
| :--- | :--- | :--- |
| **Windows (Local)** | `persona.txt` | Saves the file in the bot's project folder. |
| **Railway (Cloud)** | `/etc/secrets/persona.txt` | Saves to a persistent volume (requires mount). |
| **Linux (Server)** | `./persona.txt` | Uses a relative path in the current directory. |

**Example `.env`:**

```dotenv
BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
GOOGLE_SEARCH_API_KEY=YOUR_GOOGLE_SEARCH_API_KEY
SEARCH_ENGINE_ID=YOUR_GOOGLE_SEARCH_ENGINE_ID
WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT
WOLFRAM_APPID_LLM=YOUR_WOLFRAM_APPID_LLM
AI_PERSONA_FILE=persona.txt 
BOT_NAME="Freesona"
```

### 3. Persistence & Setup

The bot manages storage automatically to ensure your customization is never lost:

* **Fresh Install:** At startup, the bot checks for the persona file. If missing, it falls back to the `AI_PERSONA` text in your `.env` or a default greeting.
* **Auto-Creation:** The bot will automatically create the `persona.txt` file at your specified path the first time you use the `/setpersona` command.
* **Cloud Persistence:** If using Railway, ensure you have a Volume mounted to the directory specified in your `AI_PERSONA_FILE` path (e.g., `/etc/secrets`).

---

## How to Customize the Persona

1. Type **/setpersona** in your Discord server.
2. A private window (Modal) will appear. **Note:** Only the bot owner can trigger this.
3. Enter your new instructions and click **Submit**.
4. The bot updates its memory and saves to the file instantly.

## License

Licensed under the **MIT License**. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements

* [discord.py](https://discordpy.readthedocs.io/)
* [Google Gemini](https://ai.google.dev/)
* [Wolfram|Alpha](https://developer.wolframalpha.com/)
* [yt-dlp](https://github.com/yt-dlp/yt-dlp)
