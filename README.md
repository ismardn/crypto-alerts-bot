# Crypto Price Alert Discord Bot

A simple, self-hosted Discord bot for creating personal cryptocurrency price alerts. The bot monitors prices using the Kraken public API and sends a notification via a webhook when a target price is crossed.

---

## Features

- **Real-time Price Alerts:** Set price targets for any cryptocurrency pair available on Kraken.
- **Simple Command Format:** Easily create alerts in a dedicated Discord channel using the `PAIR:PRICE` format (e.g., `BTCUSD:65000`).
- **Webhook Notifications:** Receive a direct mention (`@YourUser`) in a notification channel when an alert is triggered.
- **Automatic Cleanup:** Alerts are automatically deleted once they are triggered.
- **Interactive Feedback:** The bot provides instant feedback with emoji reactions (✅ for success, ❓ for errors) on your alert messages.
- **Efficient:** Uses a single API call to fetch prices for all active alerts.
- **Secure:** Uses a `.env` file to keep your bot token and other secrets safe.

## How It Works

1.  **Set an Alert:** In your private "manager" channel, post a message with the format `PAIR:PRICE`. For example: `ETHUSD:2500`.
2.  **Bot Acknowledges:** The bot reacts with ✅ to confirm the alert has been successfully registered.
3.  **Monitoring:** Every minute, the bot fetches the latest prices from Kraken for all your active alerts.
4.  **Notification:** If a price crosses your target (either up or down), the bot sends a notification message mentioning you in your alerts channel.
5.  **Cleanup:** The original alert message in the manager channel is deleted to avoid duplicate notifications.

## Prerequisites

- Python 3.8+
- A Discord Bot Token
- A Discord Webhook URL
- IDs for your user and management channel

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ismardn/crypto-alerts-bot.git
    cd crypto-alerts-bot
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Create a `requirements.txt` file** with the following content:
    ```
    discord.py
    httpx
    python-dotenv
    ```

4.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Set up your environment variables:**
    Create a file named `.env` in the root directory and copy the contents of `.env.example` into it.

    **`.env.example`**
    ```env
    # The token for your Discord bot.
    # Go to Discord Developer Portal > Your Application > Bot > Reset Token
    CRYPTO_ALERTS_BOT_TOKEN="YOUR_BOT_TOKEN_HERE"

    # The ID of the channel where you will write your alerts (e.g., "ETHUSD:3000").
    # Right-click the channel in Discord and "Copy Channel ID".
    CRYPTO_ALERTS_MANAGER_CHANNEL_ID="YOUR_MANAGER_CHANNEL_ID_HERE"

    # The URL of the webhook that will send the notification message.
    # Go to Server Settings > Integrations > Webhooks > New Webhook.
    CRYPTO_ALERTS_WEBHOOK_URL="YOUR_WEBHOOK_URL_HERE"

    # Your personal Discord user ID to be mentioned in alerts.
    # Right-click your username in Discord and "Copy User ID".
    MY_USER_ID="YOUR_DISCORD_USER_ID_HERE"
    ```
    Fill in the values in your `.env` file. **You must enable Developer Mode in Discord's settings (Advanced section) to be able to copy IDs.**

## Usage

Once the setup is complete, simply run the bot:

```bash
python your_main_script.py
