from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from database import users as users_db


class IsAdmin(BaseFilter):
    """Только главный администратор."""
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return await users_db.is_admin(event.from_user.id)


class IsStaff(BaseFilter):
    """Администратор ИЛИ модератор."""
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return await users_db.is_staff(event.from_user.id)
