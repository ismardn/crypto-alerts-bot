from nextcord.ext import commands
import nextcord.errors
import httpx
import os
import asyncio
import sys
import traceback
import websockets
import json
import datetime


# ------------------------------- Environment variables ------------------------------- #
# Useful for receiving notifications in a different channel (and avoiding giving additional permissions to the bot)
CRYPTO_ALERTS_WEBHOOK_URL = os.getenv("CRYPTO_ALERTS_WEBHOOK_URL")
CRYPTO_ALERTS_LOGS_WEBHOOK_URL = os.getenv("CRYPTO_ALERTS_LOGS_WEBHOOK_URL")

CRYPTO_ALERTS_MANAGER_CHANNEL_ID = int(os.getenv("CRYPTO_ALERTS_MANAGER_CHANNEL_ID"))
MY_USER_ID = int(os.getenv("MY_USER_ID"))
# ------------------------------------------------------------------------------------- #*

SECONDS_REFRESH_DELAY = 30


class CryptoCog(commands.Cog):
    BINANCE_STREAMS_WEBSOCKET_URL = "wss://stream.binance.com:9443/stream?streams="
    BINANCE_BOOKTICKER_STREAM_NAME = "@bookTicker"

    DISCORD_MESSAGE_DELIMITER = ":"

    PAIR_PART_MESSAGE_INDEX = 0
    PRICE_PART_MESSAGE_INDEX = 1

    ALERT_PRICE_KEY_DICT = "alert_price"
    DISCORD_MESSAGE_OBJECT_KEY_DICT = "message_obj"

    PRICE_DATA_KEY_DICT = "data"
    PAIR_NAME_KEY_DICT = "s"
    ASK_PRICE_KEY_DICT = "a"

    CORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION = "✅"
    INCORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION = "❓"

    ADD_MESSAGE_DICT_STRING = "add"
    DELETE_MESSAGE_DICT_STRING = "del"

    BINANCE_WEBSOCKET_PAIRS_DELIMITER = "/"

    PING_SECONDS_DELAY = 20
    PONG_SECONDS_TIMEOUT = 10

    HEARTBEAT_MINUTES_DELAY = 20


    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.http_client = httpx.AsyncClient()

        self.saved_channel_messages_by_pair_name = {}

        self.current_pair_prices = {}
        self.previous_pair_prices = {}

        self.websocket_task = None

        self.last_websocket_message_datetime = None


    @commands.Cog.listener()
    async def on_ready(self):
        async for message in self.bot.get_channel(CRYPTO_ALERTS_MANAGER_CHANNEL_ID).history(oldest_first=True, limit=None):
            if self.is_message_structure_correct(message.content):
                await self.update_messages_by_pair_name_dict(message, self.ADD_MESSAGE_DICT_STRING)

        self.websocket_task = asyncio.create_task(self.run_websocket_listener())

        asyncio.create_task(self.heartbeat_task())     


    def safe_default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        
        return f"<{obj.__class__.__name__}>"


    async def heartbeat_task(self):
        await self.bot.wait_until_ready()

        while True:
            current_datetime = datetime.datetime.now()
            minutes_to_wait = self.HEARTBEAT_MINUTES_DELAY - current_datetime.minute % self.HEARTBEAT_MINUTES_DELAY
            if minutes_to_wait == 0:
                seconds_to_wait = current_datetime.second
            else:
                seconds_to_wait = minutes_to_wait * 60 - current_datetime.second
            await asyncio.sleep(seconds_to_wait)

            try:
                if self.last_websocket_message_datetime:
                    last_message_age = (datetime.datetime.now() - self.last_websocket_message_datetime).total_seconds()
                    message_age = f"{int(last_message_age)}s"
                else:
                    message_age = "never"

                await self.http_client.post(CRYPTO_ALERTS_LOGS_WEBHOOK_URL, json={
                    "content": f"```\n"
                               f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n\n"
                               f"last_websocket_message_age = {message_age}\n"
                               f"pairs_number = {len(self.saved_channel_messages_by_pair_name)}\n"
                               f"```"
                })
                
            except Exception:
                await self.http_client.post(CRYPTO_ALERTS_WEBHOOK_URL, json={
                    "content": f"⚠️ <@{MY_USER_ID}>\n### An error has occured :"
                })
                await self.http_client.post(CRYPTO_ALERTS_WEBHOOK_URL, json={
                    "content": f"```\n{traceback.format_exc()}```"
                })

                sys.exit(1)


    def is_pair_name_correct(self, pair_name):
        return pair_name.isalpha() and pair_name.isupper()


    def is_pair_price_correct(self, pair_price_string):
        for char_index in range(len(pair_price_string)):
            char = pair_price_string[char_index]
            if (not char in "0123456789.") or (char == '.' and pair_price_string[0] == '0' and char_index != 1):
                return False
        return pair_price_string != ""


    def is_message_structure_correct(self, message_content):
        message_split = message_content.split(self.DISCORD_MESSAGE_DELIMITER)
        return (
            len(message_split) == 2 and
            self.is_pair_name_correct(message_split[self.PAIR_PART_MESSAGE_INDEX]) and
            self.is_pair_price_correct(message_split[self.PRICE_PART_MESSAGE_INDEX])
        )


    async def update_messages_by_pair_name_dict(self, discord_message, action):
        message_split = discord_message.content.split(self.DISCORD_MESSAGE_DELIMITER)
        pair_name = message_split[self.PAIR_PART_MESSAGE_INDEX]

        if action == self.ADD_MESSAGE_DICT_STRING:
            new_pair_name_message_dict = {
                self.DISCORD_MESSAGE_OBJECT_KEY_DICT: discord_message,
                self.ALERT_PRICE_KEY_DICT: message_split[self.PRICE_PART_MESSAGE_INDEX]
            }

            if pair_name in self.saved_channel_messages_by_pair_name:
                self.saved_channel_messages_by_pair_name[pair_name].append(new_pair_name_message_dict)
            else:
                self.saved_channel_messages_by_pair_name[pair_name] = [new_pair_name_message_dict]

                await self.restart_websocket()

        elif action == self.DELETE_MESSAGE_DICT_STRING:
            if pair_name not in self.saved_channel_messages_by_pair_name:
                return
        
            if discord_message not in [pair_name_message_dict[self.DISCORD_MESSAGE_OBJECT_KEY_DICT] for pair_name_message_dict in self.saved_channel_messages_by_pair_name[pair_name]]:
                return
            
            if len(self.saved_channel_messages_by_pair_name[pair_name]) == 1:
                del self.saved_channel_messages_by_pair_name[pair_name]

                if pair_name in self.current_pair_prices:
                    del self.current_pair_prices[pair_name]
                if pair_name in self.previous_pair_prices:
                    del self.previous_pair_prices[pair_name]
            else:
                for pair_name_message_dict_index in range(len(self.saved_channel_messages_by_pair_name[pair_name])):
                    if self.saved_channel_messages_by_pair_name[pair_name][pair_name_message_dict_index][self.DISCORD_MESSAGE_OBJECT_KEY_DICT] == discord_message:
                        del self.saved_channel_messages_by_pair_name[pair_name][pair_name_message_dict_index]
                        break


    async def run_websocket_listener(self):
        await self.bot.wait_until_ready()
        
        while True:
            try:
                pairs_to_check = self.saved_channel_messages_by_pair_name.keys()
                if not pairs_to_check:
                    await asyncio.sleep(1)
                    continue

                streams = self.BINANCE_WEBSOCKET_PAIRS_DELIMITER.join(f"{pair_name.lower()}{self.BINANCE_BOOKTICKER_STREAM_NAME}" for pair_name in pairs_to_check)

                async with websockets.connect(f"{self.BINANCE_STREAMS_WEBSOCKET_URL}{streams}", ping_interval=self.PING_SECONDS_DELAY, ping_timeout=self.PONG_SECONDS_TIMEOUT) as binance_websocket:
                    async for pair_websocket_message in binance_websocket:
                        self.last_websocket_message_datetime = datetime.datetime.now()
                        
                        json_data = json.loads(pair_websocket_message)
                        price_data = json_data[self.PRICE_DATA_KEY_DICT]
                        pair_name = price_data[self.PAIR_NAME_KEY_DICT]
                        
                        saved_channel_messages_dict_copy = self.saved_channel_messages_by_pair_name.copy()

                        if pair_name in saved_channel_messages_dict_copy:
                            current_ask_price = price_data[self.ASK_PRICE_KEY_DICT]
                            
                            if pair_name in self.current_pair_prices:
                                self.previous_pair_prices[pair_name] = self.current_pair_prices[pair_name]
                                self.current_pair_prices[pair_name] = current_ask_price

                                previous_ask_price = self.previous_pair_prices[pair_name]

                                current_ask_price_float = float(current_ask_price)
                                previous_ask_price_float = float(previous_ask_price)

                                for pair_name_message_dict in saved_channel_messages_dict_copy[pair_name]:
                                    alert_price = pair_name_message_dict[self.ALERT_PRICE_KEY_DICT]
                                    alert_price_float = float(alert_price)

                                    if previous_ask_price_float <= alert_price_float <= current_ask_price_float or previous_ask_price_float >= alert_price_float >= current_ask_price_float:
                                        await self.update_messages_by_pair_name_dict(pair_name_message_dict[self.DISCORD_MESSAGE_OBJECT_KEY_DICT], self.DELETE_MESSAGE_DICT_STRING)
                                        
                                        await self.http_client.post(CRYPTO_ALERTS_WEBHOOK_URL, json={
                                            "content": f"<@{MY_USER_ID}> ! {pair_name} pair has crossed the price of {alert_price} !"
                                        })

                                        try:
                                            await pair_name_message_dict[self.DISCORD_MESSAGE_OBJECT_KEY_DICT].delete()
                                        except nextcord.errors.NotFound:  # This error can occur if a user deletes the alert just before the script does so
                                            pass

                            else:
                                self.current_pair_prices[pair_name] = current_ask_price
                        
            except asyncio.CancelledError:
                break
            
            except websockets.ConnectionClosedError as e:
                await asyncio.sleep(1)
                continue

            except websockets.SecurityError as e:
                await asyncio.sleep(5)  # It's possible to encounter a server with too many redirects
                continue

            except Exception:
                await self.http_client.post(CRYPTO_ALERTS_WEBHOOK_URL, json={
                    "content": f"⚠️ <@{MY_USER_ID}>\n### An error has occured :"
                })
                await self.http_client.post(CRYPTO_ALERTS_WEBHOOK_URL, json={
                    "content": f"```\n{traceback.format_exc()}```"
                })

                sys.exit(1)


    async def restart_websocket(self):
        if self.websocket_task:
            self.websocket_task.cancel()
            await asyncio.sleep(1)
            try:
                await self.websocket_task
            except asyncio.CancelledError:
                pass

        self.websocket_task = asyncio.create_task(self.run_websocket_listener())


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != CRYPTO_ALERTS_MANAGER_CHANNEL_ID:
            return
        
        if self.is_message_structure_correct(message.content):
            await message.add_reaction(self.CORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION)
            await self.update_messages_by_pair_name_dict(message, self.ADD_MESSAGE_DICT_STRING)
        else:
            await message.add_reaction(self.INCORRECT_STRUCTURE_MESSAGE_EMOJI_REACTION)


    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.channel.id != CRYPTO_ALERTS_MANAGER_CHANNEL_ID:
            return
        
        if self.is_message_structure_correct(message.content):
            await self.update_messages_by_pair_name_dict(message, self.DELETE_MESSAGE_DICT_STRING)


    @commands.Cog.listener()
    async def on_message_edit(self, message_before, message_after):
        if message_before.channel.id != CRYPTO_ALERTS_MANAGER_CHANNEL_ID:
            return

        await self.update_messages_by_pair_name_dict(message_before, self.DELETE_MESSAGE_DICT_STRING)
        await message_after.delete()


async def setup(bot):
    bot.add_cog(CryptoCog(bot))
