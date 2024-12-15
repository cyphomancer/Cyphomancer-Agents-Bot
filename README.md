# Cyphomancer-Agents-Bot

Telegram Custom AI Agent Launching Bot for Cyphomancer

---

## My Telegram Bot

This repository contains a simple Telegram bot using [Telethon](https://pypi.org/project/Telethon/).

### Usage

- Start the bot in Telegram by sending `/start`.
- Use the inline buttons to create or edit AI agents.

### Security

Make sure you **never commit** your `.env` file to GitHub, as it contains sensitive information.

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
