import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN
from database.db import init_db
from middlewares.access import AccessMiddleware

from handlers import (
    start, profile, topup, shop, trading, withdraw, tickets, moderator, admin,
    usercards, transfer, craft, craft_admin,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("star_card_bot")


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь по командам"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="shop", description="Магазин карт"),
        BotCommand(command="market", description="Биржа / курсы карт"),
        BotCommand(command="topup", description="Пополнить баланс"),
        BotCommand(command="withdraw", description="Вывести звёзды"),
        BotCommand(command="transfer", description="Перевести звёзды другому"),
        BotCommand(command="support", description="Поддержка"),
        BotCommand(command="admin_help", description="Команды администратора"),
        BotCommand(command="moderator_help", description="Команды модератора"),
        BotCommand(command="stats", description="Статистика (админ)"),
    ]
    await bot.set_my_commands(commands)


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Укажите BOT_TOKEN в config.py или переменной окружения BOT_TOKEN перед запуском."
        )

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    access_mw = AccessMiddleware()
    dp.message.outer_middleware(access_mw)
    dp.callback_query.outer_middleware(access_mw)

    # ВАЖНО: сначала специфичные роутеры (admin/moderator фильтруют доступ сами),
    # затем общие пользовательские.
    dp.include_router(admin.router)
    dp.include_router(craft_admin.router)
    dp.include_router(moderator.router)
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(topup.router)
    dp.include_router(shop.router)
    dp.include_router(trading.router)
    dp.include_router(craft.router)
    dp.include_router(withdraw.router)
    dp.include_router(tickets.router)
    dp.include_router(usercards.router)
    dp.include_router(transfer.router)

    await set_commands(bot)

    logger.info("Star Card bot запущен, начинаем polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
