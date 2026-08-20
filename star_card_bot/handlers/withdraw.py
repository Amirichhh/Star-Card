from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import users as users_db, withdraw as wd_db
from config import MIN_WITHDRAW, ADMIN_IDS
from states import Withdraw
from keyboards.user_kb import confirm_kb
from keyboards.admin_kb import withdraw_review_kb

router = Router(name="withdraw")


@router.message(F.text == "💸 Вывод звёзд")
@router.message(F.text == "/withdraw")
async def withdraw_start(message: Message, state: FSMContext):
    user = await users_db.get_user(message.from_user.id)
    if user["balance"] < MIN_WITHDRAW:
        await message.answer(f"❗ Минимальная сумма вывода — ⭐ {MIN_WITHDRAW}. "
                              f"Ваш баланс: ⭐ {user['balance']:.2f}.")
        return
    await state.set_state(Withdraw.amount)
    await message.answer(
        f"💸 Сколько звёзд вывести? (мин. {MIN_WITHDRAW}, у вас ⭐ {user['balance']:.2f})"
    )


@router.message(Withdraw.amount)
async def withdraw_amount(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().replace(".", "", 1).isdigit():
        await message.answer("❗ Введите число.")
        return
    amount = float(message.text.strip())
    user = await users_db.get_user(message.from_user.id)
    if amount < MIN_WITHDRAW:
        await message.answer(f"❗ Минимальная сумма вывода — ⭐ {MIN_WITHDRAW}.")
        return
    if amount > user["balance"]:
        await message.answer("❗ У вас недостаточно звёзд на балансе.")
        return
    await state.update_data(amount=amount)
    await state.set_state(Withdraw.requisites)
    await message.answer("✍️ Укажите, куда вывести (username получателя / реквизиты):")


@router.message(Withdraw.requisites)
async def withdraw_requisites(message: Message, state: FSMContext):
    await state.update_data(requisites=message.text.strip())
    data = await state.get_data()
    await state.set_state(Withdraw.confirm)
    await message.answer(
        f"📋 Проверьте заявку:\n\nСумма: ⭐ {data['amount']:.2f}\nКуда: {data['requisites']}\n\n"
        f"После подтверждения звёзды спишутся с баланса до одобрения заявки модератором.",
        reply_markup=confirm_kb("withdraw_confirm"),
    )


@router.callback_query(F.data == "withdraw_confirm", Withdraw.confirm)
async def withdraw_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    user = await users_db.get_user(callback.from_user.id)
    if user["balance"] < data["amount"]:
        await callback.answer("❌ Недостаточно звёзд", show_alert=True)
        return

    await users_db.change_balance(callback.from_user.id, -data["amount"], "withdraw_hold",
                                   "Резерв на вывод звёзд")
    req_id = await wd_db.create_withdraw_request(
        callback.from_user.id, callback.from_user.username, data["amount"], data["requisites"]
    )
    await callback.answer("✅ Заявка создана!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Заявка #{req_id} на вывод ⭐ {data['amount']:.2f} отправлена на рассмотрение."
    )

    notify_text = (
        f"💸 <b>Новая заявка на вывод #{req_id}</b>\n"
        f"От: @{callback.from_user.username or callback.from_user.id} (id {callback.from_user.id})\n"
        f"Сумма: ⭐ {data['amount']:.2f}\n"
        f"Куда: {data['requisites']}"
    )
    from database.users import list_moderators
    mods = await list_moderators()
    recipients = set(ADMIN_IDS) | {m["user_id"] for m in mods}
    for uid in recipients:
        try:
            await bot.send_message(uid, notify_text, parse_mode="HTML", reply_markup=withdraw_review_kb(req_id))
        except Exception:
            pass


@router.callback_query(F.data == "my_withdrawals")
async def cb_my_withdrawals(callback: CallbackQuery):
    await callback.answer()
    reqs = await wd_db.list_user_withdrawals(callback.from_user.id)
    if not reqs:
        await callback.message.answer("У вас пока нет заявок на вывод.")
        return
    status_icons = {"pending": "⏳", "approved": "✅", "declined": "❌"}
    lines = [
        f"{status_icons.get(r['status'], '•')} #{r['request_id']} — ⭐ {r['amount']:.2f} ({r['status']})"
        for r in reqs
    ]
    await callback.message.answer("📜 <b>Ваши заявки на вывод:</b>\n\n" + "\n".join(lines), parse_mode="HTML")
