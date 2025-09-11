import logging
import asyncio
import os
import sys

import aiogram
import dotenv
import httpx
from aiogram import filters as tg_filters
from aiogram import types as tg_types

dotenv.load_dotenv(".env")

CLYRE_BACKEND_URL = os.getenv("CLYRE_BACKEND_URL")
SYNC_RESPONSE_ENDPOINT = os.getenv("SYNC_RESPONSE_ENDPOINT")
BOT_TOKEN = os.getenv("API_TOKEN")


async def get_response(message: str, tg_user_id: str, thread_id: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=100) as client:
        response = await client.post(CLYRE_BACKEND_URL + SYNC_RESPONSE_ENDPOINT, json={
            "user_id": tg_user_id,
            "message": message if len(message) <= 500 else message[:500],
            "thread_id": thread_id
        })

        return response.json()


dp = aiogram.Dispatcher()
history = {}


@dp.message(tg_filters.Command("start"))
async def cmd_start(message: aiogram.types.Message):
    await message.reply("Hello! I'm your friendly bot. How can I assist you today?")


@dp.message(tg_filters.Command("reset"))
async def cmd_reset(message: aiogram.types.Message):
    if history.get(message.chat.id):
        del history[message.chat.id]
    await message.reply(
        "Your conversation has been reset. "
        "Previous messages has no value now. "
        "How can I assist you now?"
    )


@dp.message()
async def handle_message(message: aiogram.types.Message):
    try:
        if history.get(message.chat.id) is None:
            response = await get_response(message.text, str(message.from_user.id))
            thread_id = response.get("thread_id")
            history[message.chat.id] = thread_id
        else:
            thread_id = history[message.chat.id]
            response = await get_response(message.text, str(message.from_user.id), thread_id)
        await message.reply(response.get("response"))
    except:
         await message.reply("Something went wrong while asnwering.")


async def set_commands(bot: aiogram.Bot):
    commands = [
        tg_types.BotCommand(command="/start", description="Start the bot"),
        tg_types.BotCommand(command="/reset", description="Reset the conversation history"),
    ]
    await bot.set_my_commands(commands)


async def main():
    bot = aiogram.Bot(token=BOT_TOKEN)
    await set_commands(bot)
    dp.startup.register(lambda: logging.info("Bot started"))
    dp.shutdown.register(lambda: logging.info("Bot stopped"))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
