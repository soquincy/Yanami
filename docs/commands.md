# Command Reference

Default prefix is `~`. Change it with `~prefix <symbol>`. All commands work as both prefix and slash commands unless noted.

## AI

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `~write <prompt>` | Structured output using active persona | Anyone |
| `~ask <question>` | Conversational response using active persona | Anyone |
| `~search <query>` | Web search with AI summary | Anyone |
| `~separate <url>` | Vocal/instrumental separation via MVSEP | Anyone |

## Conversation Channel

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/setchannel #channel` | Set the AI conversation channel | Administrator |
| `/clearchannel` | Remove the conversation channel | Administrator |
| `/clearmemory` | Wipe short-term channel memory and summary | Administrator |

## Persona

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/setpersona core` | Edit core personality and background | Bot Owner |
| `/setpersona style` | Edit beliefs, language style, system instructions | Bot Owner |
| `/personalock` | Lock persona against changes | Bot Owner |
| `/personaunlock` | Unlock persona | Bot Owner |
| `/personasave <name>` | Save current persona as a preset | Bot Owner |
| `/personaload <name>` | Load a saved persona preset | Bot Owner |
| `/personalist` | List all saved presets | Bot Owner |
| `/personadelete <name>` | Delete a saved preset | Bot Owner |
| `/debugpersona` | Show active persona, last prompt, model, lock state, autonomy | Bot Owner |

## Autonomy

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `/autonomy on` | Enable autonomous mode | Administrator |
| `/autonomy off` | Disable autonomous mode | Administrator |
| `/autonomy frequency <low/default/high>` | Set confidence threshold | Administrator |

## Moderation & Utility

| Command | Action | Permissions |
| :--- | :--- | :--- |
| `~prefix <symbol>` | Change command prefix | Administrator |
| `~purge <limit>` | Delete messages | Manage Messages |
| `~math <equation>` | Solve an equation | Anyone |
| `~download <url>` | Download video | Anyone |
| `~audio <url>` | Download audio as MP3 | Anyone |
