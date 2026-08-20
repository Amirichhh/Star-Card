from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import tickets as tickets_db, users as users_db
from config import ADMIN_IDS
from states import SupportTicket
from keyboards.user_kb import ticket_user_kb

router = Router(name="tickets")


@router.message(F.text == "🆘 Поддержка")
@router.message(F.text == "/support")
async def support_entry(message: Message, state: FSMContext):
    ticket = await tickets_db.get_open_ticket_for_user(message.from_user.id)
    if ticket:
        await state.set_state(SupportTicket.chatting)
        await state.update_data(ticket_id=ticket["ticket_id"])
        await message.answer(
            f"💬 У вас уже есть открытое обращение #{ticket['ticket_id']}.\n"
            f"Просто напишите сообщение, чтобы продолжить диалог.",
            reply_markup=ticket_user_kb(ticket["ticket_id"]),
        )
        return
    await state.set_state(SupportTicket.subject)
    await message.answer("🆘 Опишите вашу проблему одним сообщением:")


@router.message(SupportTicket.subject)
async def create_ticket(message: Message, state: FSMContext, bot: Bot):
    subject = message.text.strip()
    ticket_id = await tickets_db.create_ticket(message.from_user.id, message.from_user.username, subject)
    await tickets_db.add_message(ticket_id, message.from_user.id, "user", subject)

    await state.set_state(SupportTicket.chatting)
    await state.update_data(ticket_id=ticket_id)
    await message.answer(
        f"✅ Обращение #{ticket_id} создано! Модератор скоро подключится.\n"
        f"Вы можете продолжать писать сюда — сообщения будут добавляться к обращению.",
        reply_markup=ticket_user_kb(ticket_id),
    )

    from database.users import list_moderators
    mods = await list_moderators()
    recipients = set(ADMIN_IDS) | {m["user_id"] for m in mods}
    text = f"🎫 <b>Новое обращение #{ticket_id}</b>\nОт: @{message.from_user.username or message.from_user.id}\n\n{subject}"
    for uid in recipients:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception:
            pass


@router.message(SupportTicket.chatting)
async def continue_ticket(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = await tickets_db.get_ticket(ticket_id) if ticket_id else None
    if not ticket or ticket["status"] != "open":
        await state.clear()
        await message.answer("Это обращение уже закрыто. Напишите 🆘 Поддержка, чтобы открыть новое.")
        return

    await tickets_db.add_message(ticket_id, message.from_user.id, "user", message.text or "[вложение]")
    await message.answer("✅ Сообщение добавлено к обращению.", reply_markup=ticket_user_kb(ticket_id))

    staff_id = ticket["claimed_by"]
    if staff_id:
        try:
            await bot.send_message(staff_id, f"✉️ Новое сообщение по обращению #{ticket_id}:\n\n{message.text}")
        except Exception:
            pass


@router.callback_query(F.data.startswith("close_ticket:"))
async def cb_close_ticket_by_user(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split(":")[1])
    ticket = await tickets_db.get_ticket(ticket_id)
    if not ticket or ticket["user_id"] != callback.from_user.id:
        await callback.answer("❌ Это не ваше обращение", show_alert=True)
        return
    await tickets_db.close_ticket(ticket_id, callback.from_user.id)
    await state.clear()
    await callback.answer("✅ Обращение закрыто")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Обращение закрыто. Спасибо за обращение!")
