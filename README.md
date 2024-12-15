# Cyphomancer-Agents-Bot

Telegram Custom AI Agent Launching Bot for Cyphomancer

---

## My Telegram Bot

This repository contains a simple Telegram bot using [Telethon](https://pypi.org/project/Telethon/).

### Usage

- Start the bot in Telegram by sending `/start`.
- Use inline buttons to create or edit AI agents.

### Security & Privacy

- Make sure you **never commit** your `.env` file to GitHub, as it contains sensitive information.
- **Account Linking Notice**: By linking Telegram accounts to this bot, you grant the bot and its admins access to those accounts. **Only link Telegram accounts that you specifically use for funds or trading bots**, if applicable. Do not link personal or sensitive accounts that you do not wish to share.

### Generating an Encryption Key

This bot uses an encryption key to secure Telegram user data. You can generate a new encryption key using the `cryptography` library in Python:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

### Customization

Replace the `[LLM placeholder]` function in your code with actual logic that calls your VPS or locally hosted LLM endpoint.

---

## Setup Instructions

1. **Clone or download** this repo.

2. **Create a `.env` file** (in the same folder as `bot.py`) with the following format:
    ```
    API_ID=XXXX
    API_HASH=XXXX
    BOT_TOKEN=XXXX
    ENCRYPTION_KEY=XXXX
    GROUP_ID=-100XXXXXXXXX
    ```
   
3. **Install dependencies**:
    ```bash
    pip install telethon python-dotenv cryptography
    ```

4. **Run the bot**:
    ```bash
    python bot.py
    ```

---

Feel free to adjust any section titles or descriptions to better reflect your project’s specifics.
