import asyncio
import logging
import os
import traceback

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
import uvicorn

from db import init_db, add_user, get_random_track
from admin_web import create_app
import messages as msg


# ---------- ENV ----------
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

# Можно указать ID админов, если потом решим что-то делать с ними
ADMIN_IDS = {
    int(x)
    for x in os.getenv("ADMIN_IDS", "").replace(";", ",").split(",")
    if x.strip().isdigit()
}


# ---------- LOGGING ----------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ---------- Keyboards ----------
def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Поехали", callback_data="go"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
            ]
        ]
    )


def game_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Следующая песня", callback_data="next"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Начать сначала", callback_data="restart"
                ),
            ],
        ]
    )


# ---------- Bot handlers ----------
router = Router()


async def _send_random_track(message: Message):
    track = await get_random_track()
    if not track:
        await message.answer(msg.NO_TRACKS_TEXT)
        return

    _id, title, points, hint, is_active, created_at = track

    lines = [title]
    if points:
        lines.append(f"{points} балл(а/ов)")
    if hint:
        lines.append("")
        # Подсказка скрыта спойлером
        lines.append(f"||{hint}||")

    text = "\n".join(lines)
    await message.answer(text, reply_markup=game_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message):
    await add_user(message.from_user.id, message.from_user.username)
    await message.answer(msg.START_TEXT, reply_markup=start_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(msg.HELP_TEXT)


@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    await cb.message.answer(msg.HELP_TEXT)
    await cb.answer()


@router.callback_query(F.data.in_(["go", "next", "restart"]))
async def cb_game(cb: CallbackQuery):
    await add_user(cb.from_user.id, cb.from_user.username)
    try:
        await _send_random_track(cb.message)
    except Exception:
        logger.error("Error sending track\n%s", traceback.format_exc())
        await cb.message.answer("Произошла ошибка, попробуй ещё раз.")
    await cb.answer()


# ---------- Run bot & web ----------
async def run_bot(bot: Bot, dp: Dispatcher):
    logger.info("Starting bot polling...")
    await dp.start_polling(bot)


async def run_web(bot: Bot):
    app = create_app(bot)
    port = int(os.getenv("PORT", "8080"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    os.makedirs("uploads", exist_ok=True)
    await init_db()

    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    dp.include_router(router)

    bot_task = asyncio.create_task(run_bot(bot, dp))
    web_task = asyncio.create_task(run_web(bot))

    await asyncio.gather(bot_task, web_task)


if __name__ == "__main__":
    asyncio.run(main())
