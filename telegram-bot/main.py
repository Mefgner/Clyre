import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import aiogram
import dotenv
import httpx
from aiogram import filters as tg_filters
from aiogram import types as tg_types


class Env:
    # env scheme
    CLYRE_BACKEND_URL: str = "http://localhost:6750"
    SYNC_RESPONSE_ENDPOINT: str = "/api/chat/telegram-response"
    TG_REGISTRATION_ENDPOINT: str = "/api/auth/telegram-register"
    BOT_TOKEN: str
    HISTORY_PATH: str = "./history.json"
    SERVICE_SECRET: str

    def __init__(self) -> None:
        logging.debug("Loading env.")
        dotenv.load_dotenv(".env")

    def __getattribute__(self, name: str) -> str:
        logging.debug(f"Getting from env {name}.")
        atr = os.getenv(name)
        if not atr:
            raise ValueError("Requested env value is not set")
        return atr


env = Env()


async def get_response(
    message: str, tg_user_id: str, tg_chat_id: str, thread_id: str | None = None
) -> dict:
    logging.info("Sending request for response.")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            env.CLYRE_BACKEND_URL + env.SYNC_RESPONSE_ENDPOINT,
            json={
                "telegram_chat_id": tg_chat_id,
                "telegram_user_id": tg_user_id,
                "message": message if len(message) <= 500 else message[:500],
                "thread_id": thread_id,
            },
            headers={"Authorization": " ".join(("Service", env.SERVICE_SECRET))},
        )
        response.raise_for_status()
        return response.json()


async def register_user(tg_user_id: str, tg_chat_id: str):
    logging.info("Trying to register telegram user.")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            env.CLYRE_BACKEND_URL + env.TG_REGISTRATION_ENDPOINT,
            json={"chat_id": tg_chat_id, "user_id": tg_user_id},
            headers={"Authorization": " ".join(("Service", env.SERVICE_SECRET))},
        )
        response.raise_for_status()


dp = aiogram.Dispatcher()

history = {}


def load_history():
    global history
    if Path(env.HISTORY_PATH).is_file():
        with open(env.HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            history = {int(k): v for k, v in data.items()}


def save_history():
    with open(env.HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {str(k): v for k, v in history.items()}, f, ensure_ascii=False, indent=4
        )


@dp.message(tg_filters.Command("start"))
async def cmd_start(message: tg_types.Message):
    if message.from_user is None:
        return await message.reply("Not supported in channels.")

    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    try:
        await register_user(user_id, chat_id)
    except Exception as e:
        return await message.reply(
            f"Hello! Something went wrong, try to start me latter. \n {e}"
        )
    return await message.reply(
        "Hello! I'm your friendly bot. How can I assist you today?"
    )


@dp.message(tg_filters.Command("reset"))
async def cmd_reset(message: tg_types.Message):
    if history.get(message.chat.id):
        del history[message.chat.id]
    await message.reply(
        "Your conversation has been reset. "
        "Previous messages has no value now. "
        "How can I assist you now?"
    )


@dp.message()
async def handle_message(message: tg_types.Message):
    if message.from_user is None:
        return await message.reply("Not supported in channels.")
    if not message.text:
        return await message.reply("Supported only text question yet.")

    chat_id = message.chat.id
    user_id = message.from_user.id

    try:
        if history.get(message.chat.id) is None:
            response = await get_response(message.text, str(user_id), str(chat_id))
            thread_id = response.get("thread_id")
            history[message.chat.id] = thread_id
        else:
            thread_id = history[message.chat.id]
            response = await get_response(
                message.text, str(user_id), str(chat_id), thread_id
            )
        await message.reply(
            response.get("response", ""), parse_mode=aiogram.enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        await message.reply(f"Something went wrong while answering. \n {e}")


async def set_commands(bot: aiogram.Bot):
    commands = [
        tg_types.BotCommand(command="/start", description="Start the bot"),
        tg_types.BotCommand(
            command="/reset", description="Reset the conversation history"
        ),
    ]
    await bot.set_my_commands(commands)


async def main():
    bot = aiogram.Bot(token=env.BOT_TOKEN)
    await set_commands(bot)
    dp.startup.register(load_history)
    dp.shutdown.register(save_history)
    dp.shutdown.register(bot.session.close)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    asyncio.run(main())
