from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database import users as users_db
from services.subscription import get_unsubscribed_channels
from keyboards.user_kb import subscribe_kb

# callback_data, которые должны проходить всегда (даже без подписки/до проверки)
ALWAYS_ALLOWED_CALLBACKS = {"check_subscription"}


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        await users_db.ensure_user(user.id, user.username, user.full_name)
        db_user = await users_db.get_user(user.id)

        if db_user and db_user["is_banned"]:
            text = "⛔ Вы заблокированы в этом боте."
            if db_user["ban_reason"]:
                text += f"\nПричина: {db_user['ban_reason']}"
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return

        # Админов не блокируем требованием подписки, чтобы они всегда могли администрировать бота
        is_admin = await users_db.is_admin(user.id)

        callback_data = event.data if isinstance(event, CallbackQuery) else None
        if callback_data in ALWAYS_ALLOWED_CALLBACKS:
            return await handler(event, data)

        if not is_admin:
            bot = data["bot"]
            missing = await get_unsubscribed_channels(bot, user.id)
            if missing:
                # Сохраняем deep-link пейлоад /start (например код чека), чтобы обработать
                # его сразу после подтверждения подписки.
                if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                    parts = event.text.split(maxsplit=1)
                    if len(parts) > 1:
                        state = data.get("state")
                        if state is not None:
                            await state.update_data(pending_start_payload=parts[1].strip())

                text = (
                    "🔒 Для использования бота <b>Star Card</b> подпишитесь на наши каналы:\n\n"
                    + "\n".join(f"• {ch['title']}" for ch in missing)
                )
                kb = subscribe_kb(missing)
                if isinstance(event, Message):
                    await event.answer(text, reply_markup=kb, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Подпишитесь на каналы, чтобы продолжить", show_alert=True)
                    await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
                return

        return await handler(event, data)
