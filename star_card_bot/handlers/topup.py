from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext

from database import users as users_db
from states import TopUp
from keyboards.user_kb import topup_amounts_kb
from config import MIN_TOPUP

router = Router(name="topup")


@router.message(F.text == "⭐ Пополнить баланс")
@router.message(F.text == "/topup")
async def topup_menu(message: Message):
    await message.answer(
        "⭐ Выберите сумму пополнения (в звёздах Telegram):",
        reply_markup=topup_amounts_kb(),
    )


async def send_stars_invoice(bot: Bot, chat_id: int, amount: int):
    await bot.send_invoice(
        chat_id=chat_id,
        title="Пополнение баланса Star Card",
        description=f"Пополнение внутреннего баланса на {amount} ⭐",
        payload=f"topup_{amount}",
        provider_token="",  # для Telegram Stars (XTR) всегда пустая строка
        currency="XTR",
        prices=[LabeledPrice(label="Пополнение баланса", amount=amount)],
    )


@router.callback_query(F.data.startswith("topup:"))
async def cb_topup(callback: CallbackQuery, state: FSMContext, bot: Bot):
    value = callback.data.split(":", 1)[1]
    await callback.answer()
    if value == "custom":
        await state.set_state(TopUp.custom_amount)
        await callback.message.answer(f"✏️ Введите сумму пополнения (мин. {MIN_TOPUP} ⭐):")
        return
    await send_stars_invoice(bot, callback.from_user.id, int(value))


@router.message(TopUp.custom_amount)
async def process_custom_topup(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("❗ Введите целое число звёзд.")
        return
    amount = int(message.text.strip())
    if amount < MIN_TOPUP:
        await message.answer(f"❗ Минимальная сумма пополнения — {MIN_TOPUP} ⭐.")
        return
    await state.clear()
    await send_stars_invoice(bot, message.from_user.id, amount)


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    amount = payment.total_amount  # в XTR это количество звёзд как есть
    await users_db.change_balance(message.from_user.id, amount, "topup",
                                   f"Пополнение через Telegram Stars ({payment.telegram_payment_charge_id})")
    await message.answer(f"✅ Баланс пополнен на ⭐ {amount}! Спасибо 💫")
