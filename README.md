# @Cyphomancer_Agents_Bot

**Telegram Custom AI Agent Launching Bot for Cyphomancer**  

![Cyphomancer Bot](42.png)

---

## Telegram Bot

This repository contains a simple Telegram bot using Telethon.

### Usage

- Start the bot in Telegram by sending `/start`.
- Use inline buttons to create or edit AI agents.

### Security & Privacy

- **Do not commit your `.env` file to GitHub**, as it contains sensitive information.
- **Account Linking Notice**: By linking Telegram accounts to this bot, you grant the bot and its admins access to those accounts. Do not link Telegram accounts used for funds or trading bots, if applicable. Do not link personal or sensitive accounts that you do not wish to share.

---

## Customization

Replace the `[LLM placeholder]` function in your code with actual logic that calls your VPS or locally hosted LLM endpoint.

---

## Setup Instructions

1. **Save the bot.py file to your server.**

2. **Create a `.env` file (in the same folder as `bot.py`) with the following format:**

   ```env
   API_ID=XXXX
   API_HASH=XXXX
   BOT_TOKEN=XXXX
   ENCRYPTION_KEY=XXXX
   GROUP_ID=-100XXXXXXXXX

3. **Configure your environment and setup environmental variables**

- API_ID and API_HASH: Obtain these from your/dev Telegram account by creating a new app at Telegram's API Development Tools.

- BOT_TOKEN: Get this from BotFather when creating your Telegram bot.

- GROUP_ID: Enter the Telegram group chat ID where members will have enhanced limits for linked accounts. You can retrieve this ID by enabling admin privileges in the group and using a bot to fetch it.

- ENCRYPTION_KEY: Generate a strong encryption key for securing user account data using this command:

    ```bash 
    openssl rand -base64 32
    ```

4. **Install dependencies**:
    ```bash
    pip install telethon python-dotenv cryptography
    ```

5. **Run the bot**:
    ```bash
    python bot.py
    ```
