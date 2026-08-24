from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import users as users_db
from config import TRANSFER_COMMISSION, MIN_TRANSFER, ADMIN_IDS
from states import TransferStars
from keyboards.user_kb import confirm_kb

router = Router(name="transfer")


@router.message(F.text == "💱 Перевести звёзды")
@router.message(F.text == "/transfer")
async def transfer_start(message: Message, state: FSMContext):
    user = await users_db.get_user(message.from_user.id)
    if user["balance"] < MIN_TRANSFER:
        await message.answer("❗ У вас недостаточно звёзд для перевода.")
        return
    await state.set_state(TransferStars.target)
    await message.answer(
        f"💱 Перевод звёзд другому пользователю (комиссия {TRANSFER_COMMISSION*100:.0f}%).\n\n"
        f"👤 Укажите ID или @username получателя:"
    )


@router.message(TransferStars.target)
async def transfer_target(message: Message, state: FSMContext):
    recipient = await users_db.resolve_user(message.text.strip())
    if not recipient:
        await message.answer("❗ Пользователь не найден. Он должен хотя бы раз запустить бота.")
        return
    if recipient["user_id"] == message.from_user.id:
        await message.answer("❗ Нельзя перевести звёзды самому себе.")
        return
    await state.update_data(target_id=recipient["user_id"], target_label=recipient["username"] or recipient["user_id"])
    await state.set_state(TransferStars.amount)
    await message.answer(f"💰 Сколько звёзд перевести пользователю @{recipient['username'] or recipient['user_id']}?")


@router.message(TransferStars.amount)
async def transfer_amount(message: Message, state: FSMContext):
    if not message.text.strip().replace(".", "", 1).isdigit():
        await message.answer("❗ Введите число.")
        return
    amount = float(message.text.strip())
    if amount < MIN_TRANSFER:
        await message.answer(f"❗ Минимальная сумма перевода — ⭐ {MIN_TRANSFER}.")
        return

    user = await users_db.get_user(message.from_user.id)
    if user["balance"] < amount:
        await message.answer("❗ У вас недостаточно звёзд на балансе.")
        return

    commission = round(amount * TRANSFER_COMMISSION, 2)
    receive = round(amount - commission, 2)
    data = await state.get_data()
    await state.update_data(amount=amount, commission=commission, receive=receive)
    await state.set_state(TransferStars.confirm)
    await message.answer(
        f"💱 Перевод @{data['target_label']}:\n\n"
        f"Спишется с вас: ⭐ {amount:.2f}\n"
        f"Комиссия ({TRANSFER_COMMISSION*100:.0f}%): -⭐ {commission:.2f}\n"
        f"<b>Получатель получит: ⭐ {receive:.2f}</b>",
        parse_mode="HTML",
        reply_markup=confirm_kb("transfer_confirm"),
    )


@router.callback_query(F.data == "transfer_confirm", TransferStars.confirm)
async def transfer_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    user = await users_db.get_user(callback.from_user.id)
    if user["balance"] < data["amount"]:
        await callback.answer("❌ Недостаточно звёзд", show_alert=True)
        return

    target_id = data["target_id"]
    await users_db.change_balance(callback.from_user.id, -data["amount"], "transfer_out",
                                   f"Перевод пользователю {target_id}")
    await users_db.change_balance(target_id, data["receive"], "transfer_in",
                                   f"Перевод от пользователя {callback.from_user.id}")
    await users_db.change_balance(ADMIN_IDS[0], data["commission"], "transfer_commission",
                                   f"Комиссия с перевода {callback.from_user.id} -> {target_id}")

    await callback.answer("✅ Переведено!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Вы перевели ⭐ {data['amount']:.2f} (получатель получил ⭐ {data['receive']:.2f}).")
    try:
        await bot.send_message(
            target_id,
            f"💱 Вам перевели ⭐ {data['receive']:.2f} от "
            f"@{callback.from_user.username or callback.from_user.id}!",
        )
    except Exception:
        pass
