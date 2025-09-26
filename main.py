import nextcord
from nextcord.ext import commands
import os
import dotenv
import asyncio


dotenv.load_dotenv()


# ------------------------------- Environment variables ------------------------------- #
BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")
# ------------------------------------------------------------------------------------- #

COGS_FOLDER_NAME = "cogs"


bot_intents = nextcord.Intents.default()
bot_intents.message_content = True

discord_bot = commands.Bot(intents=bot_intents)


async def main():
    for filename in os.listdir(f"./{COGS_FOLDER_NAME}"):
        if filename.endswith(".py"):
            discord_bot.load_extension(f'cogs.{filename[:-3]}')

    await discord_bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
