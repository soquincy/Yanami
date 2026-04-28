# Freesona - The Discord Bot You Customize

[Discord](https://discord.gg/fEHw2e2zrW)

Freesona is your Discord bot with a customizable personality. Its knowledge is limited to late 2025, so for the latest information, use the `~search` command!

## Features

Here's what Freesona can do:

* **Chat & Ask:** Use the `~write` or `~ask` command to chat with Freesona, powered by the Gemini AI.
* **Web Search:** Need up-to-date info? Use `~search <your query>` to get a summary from the web.
* **Math:** Can answer simple math questions with the Wolfram|Alpha API.
* **Greetings:** Say hello with `~hello`.
* **Date:** Find out the current date with `~today`.
* **Moderation:** (Requires appropriate permissions)
  * `~purge <amount>`: Delete a specified number of messages (1-100).
  * `~ban <member> [reason]`: Ban a member from the server.
  * `~kick <member> [reason]`: Kick a member from the server.
  * `~timeout <member> <duration> [reason]`: Timeout a member (e.g., `10s`, `5m`, `1h`, `1d`, max `28d`).
  * `~removetimeout <member>` or `~rt <member>` or `~untimeout <member>`: Remove a timeout from a member.
* **Help:** Get a list of commands with `~help`, or details on a specific command with `~help <command_name>`.

## Getting Started

To run Freesona yourself, follow these steps:

1. **Clone the repository:**

   ```bash
   git clone https://github.com/soquincy/Freesona.git
   cd Freesona
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**

   * Create a `.env` file in the same directory as your bot script.
   * Add the following environment variables, replacing the placeholders with your actual values:

     ```dotenv
     BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
     GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
     CHANNEL_ID=YOUR_DISCORD_CHANNEL_ID
     GOOGLE_CUSTOM_SEARCH_API_KEY=YOUR_GOOGLE_CUSTOM_SEARCH_API_KEY
     SEARCH_ENGINE_ID=YOUR_GOOGLE_CUSTOM_SEARCH_ENGINE_ID
     WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT
     WOLFRAM_APPID_LL=YOUR_WOLFRAM_APPID_LLM
     AI_PERSONA_FILE=persona.txt
     BOT_NAME="Freesona"
     ```

   * **`BOT_TOKEN`:** Create a bot application on the [Discord Developer Portal](https://discord.com/developers/applications) and get its token.
   * **`GOOGLE_API_KEY`:** Obtain a Gemini API key from the [Google Cloud AI Platform](https://console.cloud.google.com/vertex-ai/generative/language/get-started).
   * **`CHANNEL_ID`:** Enable Developer Mode in Discord (User Settings > Advanced), then right-click on the desired channel and select "Copy ID".
   * **`GOOGLE_CUSTOM_SEARCH_API_KEY` / `SEARCH_ENGINE_ID`:** Set up a Custom Search Engine on the [Google Cloud Console](https://console.cloud.google.com/) and obtain your API key and Search Engine ID.
   * **`WOLFRAM_APPID_SHORT` / `WOLFRAM_APPID_LL`:** Log in or create a Wolfram Account on the [Wolfram Developer Portal](https://developer.wolframalpha.com/) then get the 'LLM API' and 'Short Answers API' App IDs.
   * **`AI_PERSONA_FILE`:** Path to a plain text file that defines the bot's personality and behavior. The bot loads this at startup, so you can customize the persona without touching any code.
   * **`BOT_NAME`:** The display name the bot uses for itself. Set this to whatever you named your bot on the Discord Developer Portal.

4. **Run the bot:**

   ```bash
   python main.py
   ```

   *(Replace `bot.py` with the actual filename if you renamed it.)*

## Contributing

Contributions are welcome! If you have suggestions or want to add new features, feel free to open an issue or submit a pull request.

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements

* [discord.py](https://discordpy.readthedocs.io/) for providing the Discord API wrapper.
* [Google Generative AI](https://ai.google.dev/) for the Gemini API.
* [Google Cloud Custom Search API](https://developers.google.com/custom-search/v1/overview) for the web search functionality.
* [Wolfram|Alpha](https://developer.wolframalpha.com/) for the math API.
