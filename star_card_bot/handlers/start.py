from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import users as users_db, checks as checks_db
from keyboards.user_kb import main_menu_kb, subscribe_kb
from services.subscription import get_unsubscribed_channels

router = Router(name="start")


async def send_main_menu(message: Message, user_id: int, text: str = "Главное меню Star Card ⭐"):
    is_admin = await users_db.is_admin(user_id)
    is_staff = is_admin or await users_db.is_moderator(user_id)
    await message.answer(text, reply_markup=main_menu_kb(is_staff=is_staff, is_admin=is_admin))


async def process_start_payload(message: Message, user, payload: str):
    if payload.startswith("check_"):
        code = payload[len("check_"):]
        check = await checks_db.get_check_by_code(code)
        if not check or not check["is_active"]:
            await message.answer("❌ Этот чек недействителен или уже деактивирован.")
            return
        if check["used_activations"] >= check["max_activations"]:
            await message.answer("❌ Лимит активаций этого чека исчерпан.")
            return
        if await checks_db.has_activated(check["check_id"], user.id):
            await message.answer("⚠️ Вы уже активировали этот чек ранее.")
            return
        await checks_db.activate_check(check["check_id"], user.id)
        await users_db.change_balance(user.id, check["amount_per_user"], "check_claim",
                                       f"Активация чека {code}")
        await message.answer(
            f"🎉 Чек активирован! Начислено ⭐ {check['amount_per_user']:.2f} на баланс."
        )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None

    # если мы дошли до хендлера - подписка (или админ-статус) уже подтверждена мидлварью
    await message.answer(
        "👋 Добро пожаловать в <b>Star Card</b>!\n\n"
        "Покупайте карты за звёзды ⭐, следите за их курсом как на бирже, "
        "улучшайте карты и собирайте редкие экземпляры.",
        parse_mode="HTML",
    )
    if payload:
        await process_start_payload(message, message.from_user, payload)
    await send_main_menu(message, message.from_user.id)


@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, bot: Bot, state: FSMContext):
    missing = await get_unsubscribed_channels(bot, callback.from_user.id)
    if missing:
        await callback.answer("Вы подписались ещё не на все каналы 🙁", show_alert=True)
        return
    await callback.answer("✅ Подписка подтверждена!")
    try:
        await callback.message.delete()
    except Exception:
        pass

    data = await state.get_data()
    payload = data.get("pending_start_payload")
    if payload:
        await state.update_data(pending_start_payload=None)
        await process_start_payload(callback.message, callback.from_user, payload)

    await send_main_menu(callback.message, callback.from_user.id, "✅ Доступ открыт! Главное меню:")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


USER_HELP = (
    "ℹ️ <b>Команды пользователя Star Card</b>\n\n"
    "👤 /profile — профиль: баланс, портфель карт, прибыль\n"
    "🛍 /shop — магазин карт (покупка у бота, поиск, курс)\n"
    "📈 /market — биржа: топ карт по изменению курса за день\n"
    "⭐ /topup — пополнить баланс звёздами\n"
    "💸 /withdraw — подать заявку на вывод звёзд\n"
    "🆘 /support — обращение в поддержку\n\n"
    "<b>Как это работает:</b>\n"
    "1. Покупаете обычную карту в магазине по текущему курсу.\n"
    "2. Если для неё запущено улучшение — пробуете улучшить (шанс получить "
    "редкую/эпическую/мифическую/легендарную версию).\n"
    "3. Курс каждой карты растёт при покупках и падает при продажах — совсем как на бирже.\n"
    "4. Обычные карты можно продать боту мгновенно по курсу в любой момент."
)


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    await message.answer(USER_HELP, parse_mode="HTML")


@router.message(F.text == "⬅️ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await send_main_menu(message, message.from_user.id)
