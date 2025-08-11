import discord
import asyncio
import httpx
import sys
import dotenv
import os
from discord.ext import tasks
import copy


dotenv.load_dotenv()


# ------------------------------- Environment variables ------------------------------- #
CRYPTO_ALERTS_MANAGER_CHANNEL_ID = int(os.getenv("CRYPTO_ALERTS_MANAGER_CHANNEL_ID"))

MY_USER_ID = int(os.getenv("MY_USER_ID"))

# Useful for reading and deleting messages in the "crypto channel"
BOT_TOKEN = os.getenv("CRYPTO_ALERTS_BOT_TOKEN")

# Useful for receiving notifications in a different channel (and avoiding giving additional permissions to the bot)
WEBHOOK_URL = os.getenv("CRYPTO_ALERTS_WEBHOOK_URL")
# ------------------------------------------------------------------------------------- #


KRAKEN_API_PAIR_URL = "https://api.kraken.com/0/public/Ticker?pair="

MESSAGE_DELIMITER = ":"

PAIR_PART_MESSAGE_INDEX = 0
PRICE_PART_MESSAGE_INDEX = 1

RESULT_KEY_DICT = "result"
ASK_PRICE_KEY_DICT = "a"
ASK_PRICE_INDEX = 0

MINUTES_REFRESH_DELAY = 1

CORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION = "✅"
INCORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION = "❓"

ADD_MESSAGE_DICT_STRING = "add"
DELETE_MESSAGE_DICT_STRING = "del"

PAIRS_GET_PARAMETER_DELIMITER = ","


saved_channel_messages_by_pair_name = {}
previous_pair_prices = {}

data_lock = asyncio.Lock()

bot_intents = discord.Intents.default()
bot_intents.message_content = True

discord_client = discord.Client(intents=bot_intents)


async def send_alert_message(pair_name, pair_price):
    await http_client.post(WEBHOOK_URL, json={"content": f"<@{MY_USER_ID}> ! {pair_name} pair has crossed the price of {pair_price} !"})


def is_pair_name_correct(pair_name):
    for char in pair_name:
        if not (char.isalpha() and char.isupper()):
            return False
    return pair_name != ""


def is_pair_price_correct(pair_price_string):
    for char_index in range(len(pair_price_string)):
        char = pair_price_string[char_index]
        if (not char in "0123456789.") or (char == '.' and pair_price_string[0] == '0' and char_index != 1):
            return False
    return pair_price_string != ""


def is_message_structure_correct(message_content):
    message_split = message_content.split(MESSAGE_DELIMITER)
    if len(message_split) == 2:
        return is_pair_name_correct(message_split[PAIR_PART_MESSAGE_INDEX]) and is_pair_price_correct(message_split[PRICE_PART_MESSAGE_INDEX])
    return False


async def messages_by_pair_name_dict_init():
    async for message in discord_client.get_channel(CRYPTO_ALERTS_MANAGER_CHANNEL_ID).history(oldest_first=True, limit=None):
        if is_message_structure_correct(message.content):
            await update_messages_by_pair_name_dict(message, ADD_MESSAGE_DICT_STRING)


async def update_messages_by_pair_name_dict(message, action):
    message_split = message.content.split(MESSAGE_DELIMITER)

    async with data_lock:
        if action == ADD_MESSAGE_DICT_STRING:
            if message_split[PAIR_PART_MESSAGE_INDEX] in saved_channel_messages_by_pair_name:
                saved_channel_messages_by_pair_name[message_split[PAIR_PART_MESSAGE_INDEX]][message.id] = message_split[PRICE_PART_MESSAGE_INDEX]
            else:
                saved_channel_messages_by_pair_name[message_split[PAIR_PART_MESSAGE_INDEX]] = {message.id: message_split[PRICE_PART_MESSAGE_INDEX]}
        
        elif action == DELETE_MESSAGE_DICT_STRING and message.id in saved_channel_messages_by_pair_name[message_split[PAIR_PART_MESSAGE_INDEX]]:  # The message may be a message that is not saved in the dict (if it has been modified, for example).
            if len(saved_channel_messages_by_pair_name[message_split[PAIR_PART_MESSAGE_INDEX]]) == 1:
                del saved_channel_messages_by_pair_name[message_split[PAIR_PART_MESSAGE_INDEX]]
            else:
                del saved_channel_messages_by_pair_name[message_split[PAIR_PART_MESSAGE_INDEX]][message.id]


@tasks.loop(seconds=MINUTES_REFRESH_DELAY * 60)
async def check_alerts_task():
    global previous_pair_prices

    try:
        async with data_lock:
            saved_channel_messages_dict_copy = copy.deepcopy(saved_channel_messages_by_pair_name)
            
        pairs_to_check = saved_channel_messages_dict_copy.keys()
        if not pairs_to_check:
            return {}
        pairs_get_parameter = PAIRS_GET_PARAMETER_DELIMITER.join(pairs_to_check)
        
        api_response = await http_client.get(f"{KRAKEN_API_PAIR_URL}{pairs_get_parameter}")
        api_result_dict = api_response.json()[RESULT_KEY_DICT]

        current_pair_prices_dict = {}

        for pair_name in saved_channel_messages_dict_copy:
            if pair_name in api_result_dict:
                current_pair_price = api_result_dict[pair_name][ASK_PRICE_KEY_DICT][ASK_PRICE_INDEX]
            else:
                api_response_pair = await http_client.get(f"{KRAKEN_API_PAIR_URL}{pair_name}")
                api_result_dict_pair = api_response_pair.json()[RESULT_KEY_DICT]
                current_pair_price = api_result_dict_pair[list(api_result_dict_pair.keys())[0]][ASK_PRICE_KEY_DICT][ASK_PRICE_INDEX]

            current_pair_prices_dict[pair_name] = current_pair_price

            if pair_name in previous_pair_prices:
                for message_id in saved_channel_messages_dict_copy[pair_name]:
                    alert_price = saved_channel_messages_dict_copy[pair_name][message_id]

                    previous_price_float = float(previous_pair_prices[pair_name])
                    current_price_float = float(current_pair_prices_dict[pair_name])
                    alert_price_float = float(alert_price)

                    if previous_price_float <= alert_price_float <= current_price_float or previous_price_float >= alert_price_float >= current_price_float:
                        await send_alert_message(pair_name, alert_price)

                        alert_message = await discord_client.get_channel(CRYPTO_ALERTS_MANAGER_CHANNEL_ID).fetch_message(message_id)
                        await alert_message.delete()
                        await update_messages_by_pair_name_dict(alert_message, DELETE_MESSAGE_DICT_STRING)

        previous_pair_prices = current_pair_prices_dict

    except Exception as e:
        await http_client.post(WEBHOOK_URL, json={"content": f"⚠️ <@{MY_USER_ID}>\nAn error has occured : \"{e}\"\nThe bot has been disconnected."})
        sys.exit()


@discord_client.event
async def on_ready():
    global http_client

    http_client = httpx.AsyncClient()

    await messages_by_pair_name_dict_init()
    
    check_alerts_task.start()


@discord_client.event
async def on_message(message):
    if is_message_structure_correct(message.content):
        await update_messages_by_pair_name_dict(message, ADD_MESSAGE_DICT_STRING)
        await message.add_reaction(CORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION)
    else:
        await message.add_reaction(INCORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION)


@discord_client.event
async def on_message_delete(message):
    await update_messages_by_pair_name_dict(message, DELETE_MESSAGE_DICT_STRING)


@discord_client.event
async def on_message_edit(message_before, message_after):
    await update_messages_by_pair_name_dict(message_before, DELETE_MESSAGE_DICT_STRING)
    await message_after.delete()


discord_client.run(BOT_TOKEN)
