from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from database import users as users_db, inventory as inv_db, cards as cards_db
from config import RARITY_NAMES, RARITY_MULTIPLIERS
from keyboards.user_kb import profile_kb, my_cards_kb, group_view_kb
from services.image import render_card_image

router = Router(name="profile")


async def _unit_value_and_change(g):
    """Возвращает (текущая цена за 1 шт, дневное изменение % базовой карты, метка)."""
    if g["card_type"] == "base":
        card = await cards_db.get_card(g["card_ref_id"])
        if not card:
            return 0.0, 0.0, "❓ Неизвестная карта"
        value = card["current_rate"]
        chg = cards_db.day_change_percent(card)
        return value, chg, card["name"]
    else:
        variant = await cards_db.get_variant(g["card_ref_id"])
        if not variant:
            return 0.0, 0.0, "❓ Неизвестное улучшение"
        release = await cards_db.get_release(variant["release_id"])
        card = await cards_db.get_card(release["base_card_id"]) if release else None
        if not card:
            return 0.0, 0.0, variant["name"]
        value = cards_db.variant_value(card["current_rate"], variant["rarity"])
        chg = cards_db.day_change_percent(card)
        label = f"{RARITY_NAMES.get(variant['rarity'], variant['rarity'])} «{variant['name']}»"
        return value, chg, label


async def _portfolio_summary(user_id: int):
    groups = await inv_db.list_grouped_inventory(user_id)
    total_invested = 0.0
    total_value = 0.0
    weighted_change = 0.0
    rows = []
    for g in groups:
        unit_value, chg, label = await _unit_value_and_change(g)
        current_total = unit_value * g["qty"]
        invested = g["invested"]
        profit_pct = ((current_total - invested) / invested * 100) if invested else 0.0
        total_invested += invested
        total_value += current_total
        weighted_change += current_total * chg
        rows.append({
            "card_type": g["card_type"], "ref_id": g["card_ref_id"], "qty": g["qty"],
            "label": label, "unit_value": unit_value, "current_total": current_total,
            "invested": invested, "profit_pct": profit_pct, "day_change": chg,
        })
    overall_change = (weighted_change / total_value) if total_value else 0.0
    overall_profit = ((total_value - total_invested) / total_invested * 100) if total_invested else 0.0
    return rows, total_invested, total_value, overall_profit, overall_change


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    await render_profile(message, message.from_user.id)


async def render_profile(message: Message, user_id: int):
    user = await users_db.get_user(user_id)
    cards_count = await inv_db.count_user_cards(user_id)
    _, total_invested, total_value, overall_profit, overall_change = await _portfolio_summary(user_id)

    profit_icon = "🟢" if overall_profit >= 0 else "🔴"
    change_icon = "🟢" if overall_change >= 0 else "🔴"

    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"💰 Баланс: <b>⭐ {user['balance']:.2f}</b>\n"
        f"🗂 Карт в коллекции: <b>{cards_count}</b>\n\n"
        f"📦 Стоимость портфеля сейчас: <b>⭐ {total_value:.2f}</b>\n"
        f"💵 Вложено всего: ⭐ {total_invested:.2f}\n"
        f"{profit_icon} Прибыль/убыток: <b>{overall_profit:+.2f}%</b>\n"
        f"{change_icon} Изменение за сегодня: <b>{overall_change:+.2f}%</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=profile_kb())


@router.callback_query(F.data == "back_profile")
async def cb_back_profile(callback: CallbackQuery):
    await callback.answer()
    await render_profile(callback.message, callback.from_user.id)


@router.callback_query(F.data == "my_cards")
async def cb_my_cards(callback: CallbackQuery):
    await callback.answer()
    rows, *_ = await _portfolio_summary(callback.from_user.id)
    if not rows:
        await callback.message.answer("У вас пока нет карт. Загляните в 🛍 Магазин карт!")
        return
    groups = []
    for r in rows:
        icon = "🟢" if r["profit_pct"] >= 0 else "🔴"
        groups.append({
            "card_type": r["card_type"], "ref_id": r["ref_id"],
            "label": f"{r['label']} ×{r['qty']} — ⭐ {r['current_total']:.2f} ({icon}{r['profit_pct']:+.1f}%)",
        })
    await callback.message.answer("🗂 <b>Ваши карты</b> (сгруппировано):", parse_mode="HTML",
                                   reply_markup=my_cards_kb(groups))


async def _group_photo_info(card_type: str, ref_id: int):
    """Возвращает (photo_file_id, rarity) для карточки/варианта улучшения."""
    if card_type == "base":
        card = await cards_db.get_card(ref_id)
        return (card["photo_file_id"], None) if card else (None, None)
    variant = await cards_db.get_variant(ref_id)
    return (variant["photo_file_id"], variant["rarity"]) if variant else (None, None)


@router.callback_query(F.data.startswith("group_view:"))
async def cb_group_view(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    _, card_type, ref_id = callback.data.split(":")
    ref_id = int(ref_id)
    qty = await inv_db.count_owned(callback.from_user.id, card_type, ref_id)
    if qty == 0:
        await callback.message.answer("У вас больше нет таких карт.")
        return

    has_release = False
    if card_type == "base":
        release = await cards_db.get_active_release_for_card(ref_id)
        has_release = release is not None

    g = {"card_type": card_type, "card_ref_id": ref_id, "qty": qty, "invested": 0}
    unit_value, chg, label = await _unit_value_and_change(g)
    total = unit_value * qty

    text = (
        f"🃏 <b>{label}</b>\n\n"
        f"Количество: <b>{qty} шт.</b>\n"
        f"Курс за 1 шт.: ⭐ {unit_value:.2f}\n"
        f"Изменение за сегодня: {chg:+.2f}%\n"
        f"Стоимость всех: <b>⭐ {total:.2f}</b>"
    )
    kb = group_view_kb(card_type, ref_id, has_release)

    photo_file_id, rarity = await _group_photo_info(card_type, ref_id)
    if photo_file_id:
        photo = await render_card_image(bot, photo_file_id, label, unit_value, rarity, chg)
        if photo:
            await callback.message.answer_photo(photo, caption=text, parse_mode="HTML", reply_markup=kb)
            return
        # если рендер не удался — отправляем исходное фото карты как запасной вариант
        await callback.message.answer_photo(photo_file_id, caption=text, parse_mode="HTML", reply_markup=kb)
        return

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
