# Crypto Alerts Bot – aiogram & Binance WebSocket

A high-performance, real-time cryptocurrency price monitoring tool. This bot uses **Binance WebSockets** to track prices with millisecond latency and notifies you instantly via Telegram when your targets are hit.



---

## Features

* **Real-Time Surveillance**: Direct connection to Binance BookTicker streams.
* **Smart Dashboard**: A live, pinned "Control Panel" message that updates automatically.
* **Memecoin Friendly**: Specialized formatting for low-priced tokens (e.g., `0.0₅64` instead of `0.0000064`).
* **Zero-Lag Architecture**: In-memory caching for instant price comparison.
* **Robust Persistence**: SQLite database backend ensures no alerts are lost on restart.

---

## Setup & Installation

### 1. Requirements
* Python 3.9+
* Dependencies: `pip install -r requirements.txt`

### 2. Configuration
Rename `.env.example` to `.env` and fill in your credentials:
* `BOT_TOKEN`: Get it from [@BotFather](https://t.me/BotFather).
* `MY_USER_ID`: Your numerical Telegram ID (the bot only responds to you).
* `LOG_CHANNEL_ID`: The ID of the channel where you want the alerts to be posted.

---

## How to Use

### 1. Initialization
Once the bot is running, send the `/start` command in your private chat. 
* **The Dashboard**: The bot will send and **pin** a message titled `📡 ACTIVE MONITORING`. 
* This message is your "Live Hub". All active alerts will appear here as interactive buttons.

### 2. Adding an Alert
Use the `/add` command followed by the pair and your target price.
* **Syntax**: `/add BASE/QUOTE PRICE`
* **Example**: `/add BTC/USDT 100000`

> **Note**: The bot supports any valid pair listed on Binance. It automatically converts the ticker to lowercase for the WebSocket stream.

### 3. Managing Alerts (The Dashboard)
The pinned Dashboard is dynamic:
* **Real-time Update**: As soon as you add an alert, the dashboard refreshes to show the new button.
* **Easy Deletion**: Click on any alert button in the dashboard.
    * The bot will ask for **confirmation** (to avoid accidental deletions).
    * Click **✅ Confirm** to delete or **❌ Cancel** to go back.
* **Auto-Cleanup**: When an alert is triggered, the dashboard removes the button automatically.



---

## Alert Logic & Visuals

### Smart Formatting
For tokens worth less than 0.0001, the bot uses **subscript notation** to make counting zeros easier:
* Standard: `0.00000642`
* **Bot Output**: `0.0₅642`

### Notifications
When a price target is crossed, the bot sends a detailed message to your Log Channel:
* **📈 Cross Up**: If the price rises above your target.
* **📉 Cross Down**: If the price falls below your target.

---

## Technical Architecture

1.  **WebSocket Manager**: Manages a single, optimized connection to Binance. It restarts only when the set of monitored pairs changes.
2.  **In-Memory Cache**: Active alerts are stored in a RAM dictionary (`active_alerts_cache`) for O(1) lookup during high-speed price updates.
3.  **State Synchronization**: Every change is mirrored between the SQLite DB and the Python dictionaries to ensure 100% data integrity.
