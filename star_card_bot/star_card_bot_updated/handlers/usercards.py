from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import cards as cards_db, users as users_db
from config import CUSTOM_CARD_START_PRICE, CUSTOM_CARD_APPROVAL_FEE, ADMIN_IDS
from states import CreateUserCard
from keyboards.admin_kb import stock_choice_kb, card_review_kb
from keyboards.user_kb import confirm_kb, my_created_cards_kb, created_card_status_kb

router = Router(name="usercards")


# ============================================================
#   СОЗДАНИЕ СВОЕЙ КАРТЫ (уходит на модерацию)
# ============================================================

@router.message(F.text == "🖌 Создать свою карту")
async def create_user_card_start(message: Message, state: FSMContext):
    await state.set_state(CreateUserCard.photo)
    await message.answer(
        f"🖌 Создание своей карты.\n"
        f"Стартовая цена всегда ⭐ {CUSTOM_CARD_START_PRICE}. "
        f"После одобрения модератором с вас спишется ⭐ {CUSTOM_CARD_APPROVAL_FEE}.\n\n"
        f"📸 Пришлите фото карты:"
    )


@router.message(CreateUserCard.photo, F.photo)
async def create_user_card_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(CreateUserCard.name)
    await message.answer("✏️ Введите название карты:")


@router.message(CreateUserCard.photo)
async def create_user_card_photo_invalid(message: Message):
    await message.answer("❗ Пришлите именно фото.")


@router.message(CreateUserCard.name)
async def create_user_card_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CreateUserCard.description)
    await message.answer("📝 Введите описание карты (или «-», если без описания):")


@router.message(CreateUserCard.description)
async def create_user_card_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description=None if desc == "-" else desc)
    await state.set_state(CreateUserCard.stock_choice)
    await message.answer("📦 Тираж карты:", reply_markup=stock_choice_kb())


@router.callback_query(F.data == "stock:unlimited", CreateUserCard.stock_choice)
async def create_user_card_unlimited(callback: CallbackQuery, state: FSMContext):
    await state.update_data(stock_total=None)
    await callback.answer()
    await _show_user_card_confirm(callback.message, state)


@router.callback_query(F.data == "stock:limited", CreateUserCard.stock_choice)
async def create_user_card_limited(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateUserCard.stock_count)
    await callback.answer()
    await callback.message.answer("🔢 Введите количество экземпляров:")


@router.message(CreateUserCard.stock_count)
async def create_user_card_stock_count(message: Message, state: FSMContext):
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Введите целое число больше 0.")
        return
    await state.update_data(stock_total=int(message.text.strip()))
    await _show_user_card_confirm(message, state)


async def _show_user_card_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(CreateUserCard.confirm)
    stock_text = "♾ безграничный" if data.get("stock_total") is None else f"{data['stock_total']} шт."
    desc_text = f"\n{data['description']}" if data.get("description") else ""
    await message.answer_photo(
        data["photo_file_id"],
        caption=(f"🃏 <b>{data['name']}</b>{desc_text}\n\nСтартовая цена: ⭐ {CUSTOM_CARD_START_PRICE}\n"
                 f"Тираж: {stock_text}\n\n"
                 f"Карта уйдёт на проверку модератору/админу. Отправить?"),
        parse_mode="HTML",
        reply_markup=confirm_kb("create_user_card_confirm"),
    )


@router.callback_query(F.data == "create_user_card_confirm", CreateUserCard.confirm)
async def create_user_card_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    card_id = await cards_db.create_card(
        data["name"], data["photo_file_id"], CUSTOM_CARD_START_PRICE, callback.from_user.id,
        description=data.get("description"), stock_total=data.get("stock_total"),
        is_user_created=True, approval_status="pending",
    )
    await callback.answer("📨 Отправлено на проверку")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📨 Ваша карта отправлена на проверку модератору/админу. Мы сообщим, когда её рассмотрят!"
    )

    from database.users import list_moderators
    mods = await list_moderators()
    recipients = set(ADMIN_IDS) | {m["user_id"] for m in mods}
    stock_text = "♾ безграничный" if data.get("stock_total") is None else f"{data['stock_total']} шт."
    desc_text = f"\n{data['description']}" if data.get("description") else ""
    caption = (
        f"🗳 <b>Новая карта на проверку</b>\n\n"
        f"🃏 <b>{data['name']}</b>{desc_text}\n\n"
        f"Автор: @{callback.from_user.username or callback.from_user.id} (id {callback.from_user.id})\n"
        f"Тираж: {stock_text}\n"
        f"Стартовая цена: ⭐ {CUSTOM_CARD_START_PRICE}\n\n"
        f"При одобрении с автора спишется ⭐ {CUSTOM_CARD_APPROVAL_FEE}."
    )
    for uid in recipients:
        try:
            await bot.send_photo(uid, data["photo_file_id"], caption=caption, parse_mode="HTML",
                                  reply_markup=card_review_kb(card_id))
        except Exception:
            pass


# ============================================================
#   МОИ СОЗДАННЫЕ КАРТЫ (статус, блокировка торговли)
# ============================================================

@router.callback_query(F.data == "my_created_cards")
async def cb_my_created_cards(callback: CallbackQuery):
    await callback.answer()
    my_cards = await cards_db.list_cards_created_by(callback.from_user.id)
    if not my_cards:
        await callback.message.answer("Вы ещё не создавали свои карты. Нажмите «🖌 Создать свою карту»!")
        return
    await callback.message.answer("🖌 <b>Ваши созданные карты:</b>", parse_mode="HTML",
                                   reply_markup=my_created_cards_kb(my_cards))


@router.callback_query(F.data.startswith("my_created_card:"))
async def cb_my_created_card_detail(callback: CallbackQuery):
    card_id = int(callback.data.split(":")[1])
    card = await cards_db.get_card(card_id)
    if not card or card["created_by"] != callback.from_user.id:
        await callback.answer("❌ Это не ваша карта", show_alert=True)
        return
    await callback.answer()

    status_names = {"pending": "⏳ На проверке", "approved": "✅ Одобрена", "rejected": "❌ Отклонена"}
    text = (
        f"🃏 <b>{card['name']}</b>\n\n"
        f"Статус: {status_names.get(card['approval_status'], card['approval_status'])}\n"
        f"Курс: ⭐ {card['current_rate']:.2f}\n"
        f"Тираж: {cards_db.stock_label(card)}\n\n"
        f"💡 Чтобы придержать свои экземпляры этой карты и не продавать их — "
        f"используйте холд в разделе «🗂 Мои карты» в профиле."
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=created_card_status_kb())
