from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import cards as cards_db, users as users_db, inventory as inv_db
from config import ADMIN_IDS
from services import pricing
from services.image import render_card_image
from states import ShopSearch
from keyboards.user_kb import cards_list_kb, card_view_kb

router = Router(name="shop")
PAGE_SIZE = 6


async def _render_list(message: Message, page: int, search: str | None, prefix: str, title: str):
    total = await cards_db.count_active_cards(search)
    cards = await cards_db.list_active_cards(search=search, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    has_next = (page + 1) * PAGE_SIZE < total

    if not cards:
        txt = "😔 Ничего не найдено." if search else "😔 Пока нет доступных карт."
        await message.answer(txt)
        return

    header = title
    if search:
        header += f"\n🔍 Поиск: «{search}»"
    await message.answer(header, reply_markup=cards_list_kb(cards, page, has_next, prefix, with_search=(prefix == "shop")))


@router.message(F.text == "🛍 Магазин карт")
@router.message(F.text == "/shop")
async def shop_menu(message: Message, state: FSMContext):
    await state.update_data(shop_search=None)
    await _render_list(message, 0, None, "shop", "🛍 <b>Магазин карт</b>\nВыберите карту:")


@router.callback_query(F.data.startswith("shop_page:"))
async def cb_shop_page(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    search = data.get("shop_search")
    await _render_list(callback.message, page, search, "shop", "🛍 <b>Магазин карт</b>")


@router.callback_query(F.data == "shop_search")
async def cb_shop_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ShopSearch.query)
    await callback.message.answer("🔍 Введите название карты (или его часть):")


@router.message(ShopSearch.query)
async def process_search(message: Message, state: FSMContext):
    query = message.text.strip()
    await state.clear()
    await state.update_data(shop_search=query)
    await _render_list(message, 0, query, "shop", "🔍 <b>Результаты поиска</b>")


@router.message(F.text == "📈 Биржа")
@router.message(F.text == "/market")
async def market_menu(message: Message):
    total = await cards_db.count_active_cards()
    all_cards = await cards_db.list_active_cards(limit=1000, offset=0)
    ranked = sorted(all_cards, key=lambda c: cards_db.day_change_percent(c), reverse=True)[:PAGE_SIZE]
    if not ranked:
        await message.answer("😔 Пока нет карт в обороте.")
        return
    await message.answer(
        "📈 <b>Биржа Star Card</b>\nТоп карт по изменению курса за сегодня:",
        parse_mode="HTML",
        reply_markup=cards_list_kb(ranked, 0, False, "shop"),
    )


@router.callback_query(F.data.startswith("card_view:"))
async def cb_card_view(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    card_id = int(callback.data.split(":")[1])
    card = await cards_db.get_card(card_id)
    if not card or not card["is_active"]:
        await callback.message.answer("❌ Эта карта больше недоступна.")
        return

    release = await cards_db.get_active_release_for_card(card_id)
    chg = cards_db.day_change_percent(card)

    caption = (
        f"🃏 <b>{card['name']}</b>\n\n"
        f"💫 Текущий курс: <b>⭐ {card['current_rate']:.2f}</b>\n"
        f"📊 Изменение за сегодня: {chg:+.2f}%\n"
        f"🚀 Максимум за сегодня: ⭐ {card['day_high_rate']:.2f}\n"
        f"{'⚗️ Доступно улучшение!' if release else ''}"
    )
    photo = await render_card_image(bot, card["photo_file_id"], card["name"], card["current_rate"], None, chg)
    kb = card_view_kb(card_id, card["current_rate"], release is not None)
    if photo:
        await callback.message.answer_photo(photo, caption=caption, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.answer(caption, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("buy_base:"))
async def cb_buy_base(callback: CallbackQuery):
    card_id = int(callback.data.split(":")[1])
    card = await cards_db.get_card(card_id)
    if not card or not card["is_active"]:
        await callback.answer("❌ Карта недоступна", show_alert=True)
        return

    user = await users_db.get_user(callback.from_user.id)
    price = card["current_rate"]
    if user["balance"] < price:
        await callback.answer("❌ Недостаточно звёзд на балансе", show_alert=True)
        return

    await users_db.change_balance(callback.from_user.id, -price, "buy_base", f"Покупка карты «{card['name']}»")
    # 100% выручки от продажи карт магазином идёт админу-эмитенту
    await users_db.change_balance(ADMIN_IDS[0], price, "shop_revenue", f"Продажа карты «{card['name']}»")
    await inv_db.add_to_inventory(callback.from_user.id, "base", card_id, price)

    new_rate = pricing.apply_trade(card["current_rate"], price, "buy", card["base_price"])
    await cards_db.update_card_rate(card_id, new_rate)

    await callback.answer("✅ Куплено!", show_alert=False)
    await callback.message.answer(
        f"🎉 Вы купили карту «<b>{card['name']}</b>» за ⭐ {price:.2f}!\n"
        f"Новый курс: ⭐ {new_rate:.2f}",
        parse_mode="HTML",
    )
