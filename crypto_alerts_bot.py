import asyncio
import logging
import sqlite3
import os
import json
import traceback
import datetime
import websockets
import dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


dotenv.load_dotenv()


# ------------------------------- Environment variables ------------------------------- #
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_USER_ID = int(os.getenv("MY_USER_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
# ------------------------------------------------------------------------------------- #*

BINANCE_STREAMS_WEBSOCKET_URL = "wss://stream.binance.com:9443/stream?streams="
BINANCE_BOOKTICKER_STREAM_NAME = "@bookTicker"
PING_SECONDS_DELAY = 20
PONG_SECONDS_TIMEOUT = 10

ALERTS_DATABASE_FILENAME = "crypto_alerts.db"

DATABASE_NAME = "alerts"

ALERT_ID_DATABASE_FIELD = "alert_id"
BASE_CURRENCY_DATABASE_FIELD = "base_currency"
QUOTE_CURRENCY_DATABASE_FIELD = "quote_currency"
ALERT_PRICE_DATABASE_FIELD = "alert_price"
CREATED_AT_DATABASE_FIELD = "created_at"

WARNING_EMOJI = "⚠️"
CROSS_UP_EMOJI = "📈"
CROSS_DOWN_EMOJI = "📉"
TRASH_EMOJI = "🗑️"
CLOCK_EMOJI = "🕑"
ONLINE_EMOJI = "🟢"
OFFLINE_EMOJI = "🔴"

NO_ACTIVE_ALERTS_TEXT = "💤 No active alerts"
ALERT_ALREADY_REMOVED_MESSAGE = "The alert has already been removed."
WEBSOCKET_STATUS_TEXT = "🔌  WebSocket Status:  "

CONFIRM_TEXT_BUTTON = "✅ Confirm"
CANCEL_TEXT_BUTTON = "❌ Cancel"

BINANCE_WEBSOCKET_PAIRS_DELIMITER = "/"

PRICE_DATA_KEY_DICT = "data"
PAIR_NAME_KEY_DICT = "s"
ASK_PRICE_KEY_DICT = "a"

START_BOT_COMMAND_NAME = "start"
ADD_ALERT_COMMAND_NAME = "add"

PAIR_ARGS_SEPARATOR = "/"

SYNTAX_MESSAGE = "❌ The command arguments are incorrect.\n\n💡 Usage:   `/add BASE/QUOTE PRICE`\nExample:   `/add BTC/USD 100000`"
MESSAGE_SECONDS_TIMEOUT = 10

ALERT_CALLBACK_SEPARATOR = "_"
ASK_ALERT_DELETION_PREFIX_CALLBACK = f"askdel{ALERT_CALLBACK_SEPARATOR}"
CONFIRM_ALERT_DELETION_PREFIX_CALLBACK = f"confirm{ALERT_CALLBACK_SEPARATOR}"
BACK_TO_DASHBOARD_CALLBACK = "back_to_dashboard"
ALERT_ID_INDEX = 1

ACTIVE_ALERTS_CACHE_ALERT_ID_INDEX = 0

INBOX_MESSAGE_HEADER = "[Crypto Alerts Bot]\n\n"

SUBSCRIPT_MAP = {str(digit): "₀₁₂₃₄₅₆₇₈₉"[digit] for digit in range(10)}

SYNC_STEP_MINUTES = 5


logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
message_dispatcher = Dispatcher()

database_connection = sqlite3.connect(ALERTS_DATABASE_FILENAME)
database_cursor = database_connection.cursor()
database_cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {DATABASE_NAME} (
        {ALERT_ID_DATABASE_FIELD} INTEGER PRIMARY KEY AUTOINCREMENT,
        {BASE_CURRENCY_DATABASE_FIELD} TEXT, 
        {QUOTE_CURRENCY_DATABASE_FIELD} TEXT,
        {ALERT_PRICE_DATABASE_FIELD} REAL,
        {CREATED_AT_DATABASE_FIELD} TEXT
    )
""")
database_connection.commit()

pinned_dashboard_ids = {}
last_known_prices = {}
pairs_metadata = {}
active_alerts_cache = {}

is_websocket_dead = False

websocket_task = None

is_owner_filter = F.from_user.id == MY_USER_ID


def format_alert_price(price: float) -> str:
    if price >= 1 or price == 0:
        return f"{price:g}"  # Using the ":g" format allows to adapt the formatting to each number by removing excess zeros

    full_str_price = f"{price:.15f}"
    price_decimal_part = full_str_price.split(".")[1]

    significant_price_part = price_decimal_part.lstrip("0")
    zeros_number = len(price_decimal_part) - len(significant_price_part)
    
    if zeros_number > 3:  # Python seems to display numbers in scientific notation below 10^-4 (i.e. when there are more than 4 zeros)
        sub_zeros_number = "".join(SUBSCRIPT_MAP[digit] for digit in str(zeros_number))
        significant_digits = significant_price_part.rstrip("0")

        return f"0.0{sub_zeros_number}{significant_digits}"
    
    return f"{price:g}"  # Prices between 0.0001 and 0.(9) are displayed simply.


async def send_inbox_message(message: str, level="INFO"):
    try:
        if level == "INFO":
            await bot.send_message(chat_id=LOG_CHANNEL_ID,
                                   text=f"{INBOX_MESSAGE_HEADER}{message}",
                                   parse_mode="HTML")
            
        else:
            await bot.send_message(chat_id=LOG_CHANNEL_ID,
                                   text=f"{INBOX_MESSAGE_HEADER}"
                                        f"{WARNING_EMOJI} <b>ERROR:</b>\n"
                                        f"<pre>\n{message}</pre>\n",
                                   parse_mode="HTML")

    except Exception as e:
        print(f"CRITICAL: {e}")


async def refresh_dashboard(chat_id: int):
    alerts_infos_query_result = database_cursor.execute(f"""
        SELECT {ALERT_ID_DATABASE_FIELD}, {BASE_CURRENCY_DATABASE_FIELD}, {QUOTE_CURRENCY_DATABASE_FIELD}, {ALERT_PRICE_DATABASE_FIELD}
        FROM {DATABASE_NAME}
        ORDER BY {BASE_CURRENCY_DATABASE_FIELD}
    """)
    all_alerts_infos = alerts_infos_query_result.fetchall()

    dashboard_layout = []

    if not all_alerts_infos:  # If there are no alerts in the database
        dashboard_layout.append([InlineKeyboardButton(text=NO_ACTIVE_ALERTS_TEXT, callback_data="none")])
    else:
        for alert_infos in all_alerts_infos:
            alert_id, base_currency, quote_currency, alert_price = alert_infos
            button_text = f"{base_currency} : {format_alert_price(alert_price)} {quote_currency} ({base_currency}/{quote_currency})"
            dashboard_layout.append([InlineKeyboardButton(text=button_text, callback_data=f"{ASK_ALERT_DELETION_PREFIX_CALLBACK}{alert_id}")])

    alerts_menu_interface = InlineKeyboardMarkup(inline_keyboard=dashboard_layout)

    if chat_id not in pinned_dashboard_ids:  # We check whether the dashboard associated with the user is unknown (because we store pinned dashboards based on the chat ID)
        try:
            chat_info = await bot.get_chat(chat_id)
            if chat_info.pinned_message:
                if chat_info.pinned_message.from_user.id == bot.id:
                    pinned_dashboard_ids[chat_id] = chat_info.pinned_message.message_id
        except Exception:  
            pass
    
    current_datetime = datetime.datetime.now()
    formatted_current_date = current_datetime.strftime("%d %b")
    formatted_current_time = current_datetime.strftime("%H:%M")

    status_emoji = OFFLINE_EMOJI if is_websocket_dead else ONLINE_EMOJI

    dashboard_full_title = f"{CLOCK_EMOJI}  Updated on  <code>{formatted_current_date}</code>  at  <code>{formatted_current_time}</code>\n{WEBSOCKET_STATUS_TEXT}{status_emoji}\n\n<i>Updates automatically every {SYNC_STEP_MINUTES} minutes</i>"

    is_dashboard_updated = False
    if chat_id in pinned_dashboard_ids:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=pinned_dashboard_ids[chat_id],
                text=dashboard_full_title,
                reply_markup=alerts_menu_interface,
                parse_mode="HTML"
            )
            is_dashboard_updated = True
        except Exception:
            pass

    if not is_dashboard_updated:  # "is_dashboard_updated" can be False if the dashboard is no longer in the conversation but is still stored in "pinned_dashboard_ids"
        try:
            await bot.unpin_all_chat_messages(chat_id)
        except:
            pass

        new_dashboard_message = await bot.send_message(
            chat_id=chat_id,
            text=dashboard_full_title,
            reply_markup=alerts_menu_interface,
            parse_mode="HTML"
        )
        
        pinned_dashboard_ids[chat_id] = new_dashboard_message.message_id
        try:
            await bot.pin_chat_message(chat_id, new_dashboard_message.message_id)
        except:
            pass


@message_dispatcher.callback_query(F.data == "none")  # Useful for the label button indicating that no alerts have been added, so that nothing happens if it is clicked
async def callback_none(callback: types.CallbackQuery):
    await callback.answer()


async def trigger_websocket_restart():
    global websocket_task

    if websocket_task:
        websocket_task.cancel()

    await asyncio.sleep(1)

    websocket_task = asyncio.create_task(run_websocket_listener())


async def load_pairs_metadata_from_database():
    alerts_infos_query_result = database_cursor.execute(f"""
        SELECT {ALERT_ID_DATABASE_FIELD}, {BASE_CURRENCY_DATABASE_FIELD}, {QUOTE_CURRENCY_DATABASE_FIELD}, {ALERT_PRICE_DATABASE_FIELD}
        FROM {DATABASE_NAME}
    """)

    for alert_id, base_currency, quote_currency, alert_price in alerts_infos_query_result.fetchall():
        pair_name = f"{base_currency}{quote_currency}"
        
        if pair_name not in pairs_metadata:
            pairs_metadata[pair_name] = [base_currency, quote_currency]
            active_alerts_cache[pair_name] = []

        active_alerts_cache[pair_name].append([alert_id, alert_price])


async def clean_pair_metadata_if_needed(base_currency: str, quote_currency: str):  # If the deleted alert was the last one in a certain pair, we need to delete that pair from the dictionaries.
    pair_name = f"{base_currency}{quote_currency}"
    
    specific_pair_remaining_alerts = active_alerts_cache.get(pair_name, [])

    if not specific_pair_remaining_alerts:
        pairs_metadata.pop(pair_name, None)
        last_known_prices.pop(pair_name, None)
        active_alerts_cache.pop(pair_name, None)

        await trigger_websocket_restart()  # Allows to stop following pairs that are no longer useful


async def run_websocket_listener():
    global is_websocket_dead

    while True:
        try:
            pairs_to_check = list(pairs_metadata.keys())

            if not pairs_to_check:
                await asyncio.sleep(1)
                continue
            
            websocket_stream_path = BINANCE_WEBSOCKET_PAIRS_DELIMITER.join(f"{pair_name.lower()}{BINANCE_BOOKTICKER_STREAM_NAME}" for pair_name in pairs_to_check)
            full_websocket_url = f"{BINANCE_STREAMS_WEBSOCKET_URL}{websocket_stream_path}"
            
            async with websockets.connect(full_websocket_url, ping_interval=PING_SECONDS_DELAY, ping_timeout=PONG_SECONDS_TIMEOUT) as websocket:
                async for pair_websocket_message in websocket:
                    is_websocket_dead = False

                    json_data = json.loads(pair_websocket_message)
                    if "data" not in json_data: continue  # Binance can send messages that do not contain a "data" field
                    
                    price_data = json_data[PRICE_DATA_KEY_DICT]
                    pair_name = price_data[PAIR_NAME_KEY_DICT]
                    current_ask_price = float(price_data[ASK_PRICE_KEY_DICT])
                    
                    if pair_name not in pairs_metadata: 
                        # Important to check, because if the user manually deletes an alert (and therefore it is no longer present in "pairs_metadata"),
                        # but a message is sent at the same time for this pair, then this could cause a KeyError (accessing a key that is not present in the dictionary).
                        continue
 
                    if pair_name not in last_known_prices:  # When we receive a price for the first time for this specific pair
                        last_known_prices[pair_name] = current_ask_price
                        continue

                    previous_ask_price = last_known_prices[pair_name]
                    last_known_prices[pair_name] = current_ask_price
                    
                    base_currency, quote_currency = pairs_metadata[pair_name]

                    specific_pair_alerts = active_alerts_cache.get(pair_name, [])

                    for alert_infos in specific_pair_alerts[:]:
                        # It is very important to make a copy of the "specific_pair_alerts" dictionary to browse through it,
                        # as we may need to modify this dictionary and thus cause a RuntimeError error
                        alert_id, float_alert_price = alert_infos

                        is_price_crossed_down = previous_ask_price >= float_alert_price >= current_ask_price
                        is_price_crossed_up = previous_ask_price <= float_alert_price <= current_ask_price

                        if is_price_crossed_down or is_price_crossed_up:
                            emoji_direction = CROSS_UP_EMOJI if is_price_crossed_up else CROSS_DOWN_EMOJI

                            await send_inbox_message(f"<b>An alert has been triggered!</b>\n\n"
                                                     f"{base_currency} : {format_alert_price(float_alert_price)} {quote_currency} ({base_currency}/{quote_currency}) {emoji_direction}",
                                                     "INFO")
                            
                            if alert_infos in specific_pair_alerts:  # Important to check again in case it has already been deleted manually
                                database_cursor.execute(f"""
                                    DELETE FROM {DATABASE_NAME}
                                    WHERE {ALERT_ID_DATABASE_FIELD} = ?
                                """, (alert_id,))
                                database_connection.commit()

                                specific_pair_alerts.remove(alert_infos)

                                await clean_pair_metadata_if_needed(base_currency, quote_currency)
                                await refresh_dashboard(MY_USER_ID)
        
        except asyncio.CancelledError:  # Thrown when the websocket is intentionally restarted (e.g. if the added alert contains a new pair)
            break

        except Exception:
            is_websocket_dead = True

            await send_inbox_message(traceback.format_exc(), level="ERROR")
            await asyncio.sleep(1)


@message_dispatcher.message(Command(START_BOT_COMMAND_NAME), is_owner_filter)
async def command_start(user_message: types.Message):
    await user_message.delete()
    await refresh_dashboard(user_message.chat.id)


def is_pair_name_correct(pair_name: str) -> bool:
    split_pair_name = pair_name.split(PAIR_ARGS_SEPARATOR)
    if len(split_pair_name) == 2:
        return split_pair_name[0] != "" and split_pair_name[1] != ""
    return False


def is_currency_name_correct(currency_name: str) -> bool:
    return currency_name.isalpha()


def is_pair_price_correct(pair_price_string: str) -> bool:
    try:
        return float(pair_price_string) > 0
    except ValueError:
        return False


@message_dispatcher.message(Command(ADD_ALERT_COMMAND_NAME), is_owner_filter)
async def command_add(user_message: types.Message):
    try:
        command_args = user_message.text.split()[1:]
        if len(command_args) != 2: raise ValueError

        raw_pair = command_args[0].upper()
        price_input = command_args[1]

        if not is_pair_name_correct(raw_pair):
            raise ValueError

        base_currency, quote_currency = raw_pair.split(PAIR_ARGS_SEPARATOR)

        if not is_currency_name_correct(base_currency) or not is_currency_name_correct(quote_currency) or not is_pair_price_correct(price_input):
            raise ValueError
        
        float_alert_price = float(price_input)

        database_cursor.execute(f"""
            INSERT INTO {DATABASE_NAME} 
            ({BASE_CURRENCY_DATABASE_FIELD}, {QUOTE_CURRENCY_DATABASE_FIELD}, {ALERT_PRICE_DATABASE_FIELD}, {CREATED_AT_DATABASE_FIELD}) 
            VALUES (?, ?, ?, ?)
        """, (base_currency, quote_currency, float_alert_price, datetime.datetime.now().isoformat()))
        database_connection.commit()
        
        new_alert_id = database_cursor.lastrowid  # Allows to immediately retrieve the ID that was just created by the last "INSERT" statement

        await user_message.delete()
        await refresh_dashboard(user_message.chat.id)

        pair_name = f"{base_currency}{quote_currency}"

        if pair_name not in active_alerts_cache:
            active_alerts_cache[pair_name] = []

        active_alerts_cache[pair_name].append([new_alert_id, float_alert_price])

        if pair_name not in pairs_metadata:
            pairs_metadata[pair_name] = [base_currency, quote_currency]
            await trigger_websocket_restart()

    except ValueError:
        bot_answer = await user_message.answer(SYNTAX_MESSAGE, parse_mode="Markdown")
        await asyncio.sleep(MESSAGE_SECONDS_TIMEOUT)
        try:
            await user_message.delete()
            await bot_answer.delete()
        except:
            pass


@message_dispatcher.callback_query(F.data.startswith(ASK_ALERT_DELETION_PREFIX_CALLBACK), is_owner_filter)
async def callback_ask_delete(callback: types.CallbackQuery):
    alert_id = int(callback.data.split(ALERT_CALLBACK_SEPARATOR)[ALERT_ID_INDEX])
    alert_infos_query_result = database_cursor.execute(f"""
        SELECT {BASE_CURRENCY_DATABASE_FIELD}, {QUOTE_CURRENCY_DATABASE_FIELD}, {ALERT_PRICE_DATABASE_FIELD}
        FROM {DATABASE_NAME}
        WHERE {ALERT_ID_DATABASE_FIELD} = ?
    """, (alert_id,))
    alert_infos = alert_infos_query_result.fetchone()
    
    if not alert_infos:
        await callback.answer(ALERT_ALREADY_REMOVED_MESSAGE)
        await refresh_dashboard(callback.message.chat.id)
        return

    base_currency, quote_currency, alert_price = alert_infos
    confirm_deletion_text = f"{TRASH_EMOJI} Are you sure you want to remove the alert for {base_currency} at {format_alert_price(alert_price)} {quote_currency} ? ({base_currency}/{quote_currency})"
    
    confirm_alert_deletion_layout = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=CANCEL_TEXT_BUTTON, callback_data=BACK_TO_DASHBOARD_CALLBACK),
            InlineKeyboardButton(text=CONFIRM_TEXT_BUTTON, callback_data=f"{CONFIRM_ALERT_DELETION_PREFIX_CALLBACK}{alert_id}"),
        ]
    ])
    
    await callback.message.edit_text(confirm_deletion_text, reply_markup=confirm_alert_deletion_layout)
    await callback.answer()


@message_dispatcher.callback_query(F.data == BACK_TO_DASHBOARD_CALLBACK, is_owner_filter)
async def cancel_deletion_callback(callback: types.CallbackQuery):
    await refresh_dashboard(callback.message.chat.id)
    await callback.answer()


@message_dispatcher.callback_query(F.data.startswith(CONFIRM_ALERT_DELETION_PREFIX_CALLBACK), is_owner_filter)
async def confirm_deletion_callback(callback: types.CallbackQuery):
    alert_id = int(callback.data.split(ALERT_CALLBACK_SEPARATOR)[ALERT_ID_INDEX])
    
    pair_name_list_query_result = database_cursor.execute(f"""
        SELECT {BASE_CURRENCY_DATABASE_FIELD}, {QUOTE_CURRENCY_DATABASE_FIELD}
        FROM {DATABASE_NAME}
        WHERE {ALERT_ID_DATABASE_FIELD} = ?
    """, (alert_id,))
    pair_name_list = pair_name_list_query_result.fetchone()

    if not pair_name_list:
        await callback.answer(ALERT_ALREADY_REMOVED_MESSAGE)
        await refresh_dashboard(callback.message.chat.id)
        return
    
    database_cursor.execute(f"""
        DELETE FROM {DATABASE_NAME}
        WHERE {ALERT_ID_DATABASE_FIELD} = ?
    """, (alert_id,))
    database_connection.commit()
    
    await callback.answer("Alert deleted.")
    
    base_currency, quote_currency = pair_name_list
    pair_name = f"{base_currency}{quote_currency}"

    if pair_name in active_alerts_cache:
        active_alerts_cache[pair_name] = [
            alert_infos for alert_infos in active_alerts_cache[pair_name] 
            if alert_infos[ACTIVE_ALERTS_CACHE_ALERT_ID_INDEX] != alert_id
        ]

    await clean_pair_metadata_if_needed(base_currency, quote_currency)
    await refresh_dashboard(callback.message.chat.id)


async def heartbeat_loop():
    while True:
        try:
            current_time = datetime.datetime.now()
            minutes_to_next_step = SYNC_STEP_MINUTES - (current_time.minute % SYNC_STEP_MINUTES)
            seconds_to_sleep = (minutes_to_next_step * 60) - current_time.second - (current_time.microsecond / 1_000_000)
            
            await asyncio.sleep(max(seconds_to_sleep, 0) + 0.5)
            # - The "max" function allows us to avoid a specific scenario here: the bot calculates that it should sleep until, for example, 16:10,
            # while the system clock moves to 16:10:00.001, which means that "seconds_to_sleep" variable can have a negative value
            # - "+ 0.5" ensures that we are at the next minute (and not at 16:39:59.999, for example)
            
            await refresh_dashboard(MY_USER_ID)

        except Exception as e:
            print(f"Error in heartbeat: {e}")
            await asyncio.sleep(10)


async def main():
    print("=== Bot started ===")
    
    await load_pairs_metadata_from_database()

    await refresh_dashboard(MY_USER_ID)

    global websocket_task
    websocket_task = asyncio.create_task(run_websocket_listener())
    
    asyncio.create_task(heartbeat_loop())

    await bot.delete_webhook(drop_pending_updates=True)
    await message_dispatcher.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        database_connection.close()
