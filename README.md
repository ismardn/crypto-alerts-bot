# Crypto Alerts Bot – Nextcord & Binance WebSocket

A simple, self-hosted Discord bot for creating personal cryptocurrency price alerts.  
The bot monitors **real-time prices** from Binance via WebSockets and sends a notification through a webhook when a target price is crossed.  
It also includes a lightweight heartbeat logger to track the bot’s health.

---

## Features

- **Real-time Price Alerts:** Monitor any trading pair supported by Binance’s `bookTicker` stream.
- **Simple Command Format:** Create alerts in a dedicated Discord channel using the format `PAIR:PRICE` (e.g., `BTCUSDT:65000`).
- **Webhook Notifications:** Receive a direct mention (`@YourUser`) in your alerts channel when an alert is triggered.
- **Automatic Cleanup:** Alerts are automatically removed once triggered.
- **Interactive Feedback:** ✅ if the alert is valid, ❓ if the format is wrong.
- **Efficient:** Maintains a single WebSocket connection to Binance, dynamically updated with only the pairs you want.
- **Heartbeat Logs:** Optional periodic logs (via a separate webhook) showing status (pairs, last message age, restart count, etc.).
- **Secure:** Uses a `.env` file for secrets (bot token, webhook URLs, IDs).

---

## How It Works

1. **Set an Alert** – Post in your private “manager” channel with the format `PAIR:PRICE`.  
   Example: `ETHUSDT:2500`.
2. **Bot Acknowledges** – The bot reacts with ✅ if the alert is valid.
3. **Monitoring** – The bot keeps a live WebSocket connection with Binance for the tracked pairs.
4. **Notification** – If the price crosses your target (up or down), you receive a notification in the configured alerts channel with a mention.
5. **Cleanup** – The original alert message is deleted to avoid duplicates.
6. **Heartbeat** – Every X minutes (configurable), a log webhook receives status metrics like:

   ```
   [2025-09-25 22:20:00]

   last_websocket_message_age=0s
   pairs_number=1
   ws_restarts=0
   ```

---

## Prerequisites

- Python 3.9+
- A Discord Bot Token
- A Discord Webhook URL for alerts
- A Discord Webhook URL for logs (optional, but recommended)
- IDs for your user and the manager channel

---

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ismardn/crypto-alerts-bot.git
   cd crypto-alerts-bot
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .\.venv\Scripts\activate   # Windows
   ```

3. **Install dependencies:**
   Create a `requirements.txt` with:
   ```txt
   nextcord>=2.6.0
   httpx>=0.27.0
   websockets>=12.0
   python-dotenv>=1.0.0
   ```
   Then install:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your environment variables:**
   Copy `.env.example` to `.env` and fill in your values.

   **`.env.example`**
   ```env
   # Discord bot token
   DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"

   # Webhook for triggered alerts
   CRYPTO_ALERTS_WEBHOOK_URL="YOUR_ALERTS_WEBHOOK_URL_HERE"

   # Webhook for heartbeat logs (optional but recommended)
   CRYPTO_ALERTS_LOGS_WEBHOOK_URL="YOUR_LOGS_WEBHOOK_URL_HERE"

   # Channel ID where you will write alerts (format: PAIR:PRICE)
   CRYPTO_ALERTS_MANAGER_CHANNEL_ID="YOUR_MANAGER_CHANNEL_ID_HERE"

   # Your personal Discord user ID (mentioned in alerts)
   MY_USER_ID="YOUR_DISCORD_USER_ID_HERE"
   ```

   👉 To copy IDs, enable Developer Mode in Discord (User Settings → Advanced).

---

## Usage

Run the bot:

```bash
python main.py
```

In your **manager channel**, post alerts like:
```
BTCUSDT:30000
ETHUSDT:2000
```

When conditions are met, you’ll receive a notification in the alerts channel.

---

## Notes

- Only the **crypto cog** and bot skeleton are included in this repo.  
- Other personal cogs/commands are ignored via `.gitignore`.  
- Do not commit your `.env` file (keep secrets local).  
