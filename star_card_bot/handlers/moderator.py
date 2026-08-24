from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import withdraw as wd_db, tickets as tickets_db, users as users_db
from database.db import get_setting
from config import WITHDRAW_LOG_CHANNEL_SETTING_KEY
from states import StaffReply
from keyboards.admin_kb import moderator_panel_kb, withdraw_review_kb, ticket_review_kb
from filters import IsStaff

router = Router(name="moderator")
router.message.filter(IsStaff())
router.callback_query.filter(IsStaff())


MODERATOR_HELP = (
    "🛠 <b>Команды модератора</b>\n\n"
    "💸 «Заявки на вывод» — список необработанных заявок на вывод звёзд\n"
    "🎫 «Обращения» — список открытых обращений в поддержку\n\n"
    "В каждой заявке/обращении есть кнопки:\n"
    "✅ Одобрить / ❌ Отклонить — для заявок на вывод\n"
    "✋ Взять в работу / ✍️ Ответить / ✅ Закрыть — для обращений\n\n"
    "Обращение остаётся в списке активных, пока пользователь или модератор его не закроют."
)


@router.message(F.text == "🛠 Панель модератора")
async def open_moderator_panel(message: Message):
    await message.answer("🛠 Панель модератора:", reply_markup=moderator_panel_kb())


@router.message(Command("moderator_help"))
async def moderator_help(message: Message):
    await message.answer(MODERATOR_HELP, parse_mode="HTML")


# ---------------- ВЫВОДЫ ----------------

@router.message(F.text == "💸 Заявки на вывод")
async def list_withdrawals(message: Message):
    reqs = await wd_db.list_pending_withdrawals()
    if not reqs:
        await message.answer("✅ Нет необработанных заявок на вывод.")
        return
    await message.answer(f"💸 Необработанных заявок: {len(reqs)}")
    for r in reqs:
        text = (
            f"💸 <b>Заявка #{r['request_id']}</b>\n"
            f"От: @{r['username'] or r['user_id']} (id {r['user_id']})\n"
            f"Сумма: ⭐ {r['amount']:.2f}\n"
            f"Куда: {r['requisites']}\n"
            f"Дата: {r['created_at']}"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=withdraw_review_kb(r["request_id"]))


@router.callback_query(F.data.startswith("wd_approve:"))
async def cb_wd_approve(callback: CallbackQuery, bot: Bot):
    req_id = int(callback.data.split(":")[1])
    req = await wd_db.get_withdraw_request(req_id)
    if not req or req["status"] != "pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    await wd_db.close_withdraw_request(req_id, "approved", callback.from_user.id)
    await callback.answer("✅ Одобрено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Заявка #{req_id} одобрена. Не забудьте отправить звёзды вручную получателю.")
    try:
        await bot.send_message(req["user_id"], f"✅ Ваша заявка на вывод #{req_id} (⭐ {req['amount']:.2f}) одобрена!")
    except Exception:
        pass

    log_channel = await get_setting(WITHDRAW_LOG_CHANNEL_SETTING_KEY)
    if log_channel:
        label = f"@{req['username']}" if req["username"] else f"id {req['user_id']}"
        try:
            await bot.send_message(
                log_channel,
                f"💸 Пользователю {label} выдано ⭐ {req['amount']:.2f} по заявке на вывод #{req_id}.",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("wd_decline:"))
async def cb_wd_decline(callback: CallbackQuery, bot: Bot):
    req_id = int(callback.data.split(":")[1])
    req = await wd_db.get_withdraw_request(req_id)
    if not req or req["status"] != "pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    await wd_db.close_withdraw_request(req_id, "declined", callback.from_user.id)
    await users_db.change_balance(req["user_id"], req["amount"], "withdraw_refund",
                                   f"Возврат по отклонённой заявке #{req_id}")
    await callback.answer("❌ Отклонено, звёзды возвращены пользователю")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Заявка #{req_id} отклонена, звёзды возвращены пользователю.")
    try:
        await bot.send_message(req["user_id"], f"❌ Ваша заявка на вывод #{req_id} отклонена. Звёзды возвращены на баланс.")
    except Exception:
        pass


# ---------------- ОБРАЩЕНИЯ ----------------

@router.message(F.text == "🎫 Обращения")
async def list_tickets(message: Message):
    open_tickets = await tickets_db.list_open_tickets()
    if not open_tickets:
        await message.answer("✅ Нет открытых обращений.")
        return
    await message.answer(f"🎫 Открытых обращений: {len(open_tickets)}")
    for t in open_tickets:
        claimed = f"\n👤 В работе у: {t['claimed_by']}" if t["claimed_by"] else "\n🆓 Свободно"
        text = (
            f"🎫 <b>Обращение #{t['ticket_id']}</b>\n"
            f"От: @{t['username'] or t['user_id']} (id {t['user_id']})\n"
            f"Тема: {t['subject']}{claimed}"
        )
        await message.answer(text, parse_mode="HTML",
                              reply_markup=ticket_review_kb(t["ticket_id"], t["claimed_by"] is not None))


@router.callback_query(F.data.startswith("claim_ticket:"))
async def cb_claim_ticket(callback: CallbackQuery):
    ticket_id = int(callback.data.split(":")[1])
    await tickets_db.claim_ticket(ticket_id, callback.from_user.id)
    await callback.answer("✋ Взято в работу")
    await callback.message.edit_reply_markup(reply_markup=ticket_review_kb(ticket_id, True))


@router.callback_query(F.data.startswith("reply_ticket:"))
async def cb_reply_ticket(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split(":")[1])
    messages = await tickets_db.list_messages(ticket_id)
    history = "\n".join(f"{'👤' if m['sender_role']=='user' else '🛠'} {m['text']}" for m in messages[-10:])
    await state.set_state(StaffReply.replying)
    await state.update_data(ticket_id=ticket_id)
    await callback.answer()
    await callback.message.answer(f"📜 <b>История обращения #{ticket_id}:</b>\n\n{history}\n\n"
                                   f"✍️ Введите ответ пользователю:", parse_mode="HTML")


@router.message(StaffReply.replying)
async def process_staff_reply(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    ticket = await tickets_db.get_ticket(ticket_id)
    if not ticket or ticket["status"] != "open":
        await message.answer("Это обращение уже закрыто.")
        await state.clear()
        return

    await tickets_db.add_message(ticket_id, message.from_user.id, "staff", message.text)
    await tickets_db.claim_ticket(ticket_id, message.from_user.id)
    await state.clear()
    await message.answer(f"✅ Ответ отправлен пользователю по обращению #{ticket_id}.")
    try:
        await bot.send_message(
            ticket["user_id"],
            f"🛠 Ответ поддержки по обращению #{ticket_id}:\n\n{message.text}",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("close_ticket_staff:"))
async def cb_close_ticket_staff(callback: CallbackQuery, bot: Bot):
    ticket_id = int(callback.data.split(":")[1])
    ticket = await tickets_db.get_ticket(ticket_id)
    if not ticket or ticket["status"] != "open":
        await callback.answer("Уже закрыто", show_alert=True)
        return
    await tickets_db.close_ticket(ticket_id, callback.from_user.id)
    await callback.answer("✅ Обращение закрыто")
    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await bot.send_message(ticket["user_id"], f"✅ Обращение #{ticket_id} закрыто поддержкой. Спасибо!")
    except Exception:
        pass
