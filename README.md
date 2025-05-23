# Anna - Your Quirky Discord Bot

[Discord](https://discord.gg/sbqUyn87nM)

Anna is an energetic and slightly scatterbrained Discord bot inspired by the character Anna Yanami from "Too Many Losing Heroines!". She aims to be helpful while bringing a bit of her quirky personality to your server. Her knowledge is limited to early 2023, so for the latest information, use the `~search` command!

## Features

Here's what Anna can do:

* **Chat & Ask:** Use the `~write` or `~ask` command to have a chat with Anna, powered by the Gemini AI.
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

To run Anna yourself, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/soquincy/Yanami.git
    cd Yanami
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up environment variables:**
    * Create a `.env` file in the same directory as your bot script.
    * Add the following environment variables, replacing the placeholders with your actual values:
        ```
        BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
        GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
        CHANNEL_ID=YOUR_DISCORD_CHANNEL_ID
        GOOGLE_CUSTOM_SEARCH_API_KEY=YOUR_GOOGLE_CUSTOM_SEARCH_API_KEY
        SEARCH_ENGINE_ID=YOUR_GOOGLE_CUSTOM_SEARCH_ENGINE_ID
        WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT
        WOLFRAM_APPID_FULL=YOUR_WOLFRAM_APPID_FULL
        ```
    * **Get your Discord Bot Token:** Create a bot application on the [Discord Developer Portal](https://discord.com/developers/applications) and get its token.
    * **Get your Gemini API Key:** You can obtain a Gemini API key from the [Google Cloud AI Platform](https://console.cloud.google.com/vertex-ai/generative/language/get-started).
    * **Get your Discord Channel ID:** Enable Developer Mode in Discord (User Settings > Advanced) and then right-click on the desired channel and select "Copy ID".
    * **Get your Google Custom Search API Key and Engine ID:** Set up a Custom Search Engine on the [Google Cloud Console](https://console.cloud.google.com/) and obtain your API key and Search Engine ID.
    * **Get your Wolfram|Alpha App IDs:** Log in or create a Wolfram Account [here](https://developer.wolframalpha.com/) then get 'Full Results API' and 'Short Answers API' App IDs. 

4.  **Run the bot:**
    ```bash
    python bot.py
    ```
    *(Replace `bot.py` with the actual name in case you changed it.)*

## Contributing

Contributions to the project are welcome! If you have suggestions or want to add new features, feel free to open an issue or submit a pull request.

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements

* [discord.py](https://discord.py/) for providing the Discord API wrapper.
* [Google Generative AI](https://ai.google.dev/) for the Gemini API.
* [Google Cloud Custom Search API](https://developers.google.com/custom-search/v1/overview) for the web search functionality.
* The creators of "Too Many Losing Heroines!" for the inspiration behind Anna's character.
