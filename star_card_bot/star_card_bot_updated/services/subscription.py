from aiogram import Bot
from database import channels as channels_db

NOT_MEMBER_STATUSES = ("left", "kicked")


async def get_unsubscribed_channels(bot: Bot, user_id: int):
    """Возвращает список каналов (записи БД), на которые пользователь НЕ подписан."""
    all_channels = await channels_db.list_channels()
    missing = []
    for ch in all_channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in NOT_MEMBER_STATUSES:
                missing.append(ch)
        except Exception:
            # если бот не может проверить (не админ в канале, неверный chat_id и т.п.)
            # не блокируем пользователя из-за ошибки конфигурации
            continue
    return missing


async def is_subscribed_to_all(bot: Bot, user_id: int) -> bool:
    missing = await get_unsubscribed_channels(bot, user_id)
    return len(missing) == 0
