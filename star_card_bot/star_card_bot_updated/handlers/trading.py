import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import cards as cards_db, users as users_db, inventory as inv_db, crafts as crafts_db, holdings as holdings_db
from config import ADMIN_IDS, MARKET_COMMISSION, RARITY_NAMES, RARITY_MULTIPLIERS
from services import pricing
from services.valuation import resolve_card_info
from states import AutoSell, UpgradeCards, TransferCard
from keyboards.user_kb import confirm_kb

router = Router(name="trading")


async def _resolve_unit(card_type: str, ref_id: int):
    """Возвращает (base_card_or_None, multiplier_or_None, label, unit_value).
    Для base/upgrade курс привязан к конкретной базовой карте (её курс двигается
    при продаже). Для craft курс фиксирован (ингредиенты могут быть разнородными),
    поэтому base_card = None и цена не "проседает" от продажи."""
    if card_type == "craft":
        recipe = await crafts_db.get_recipe(ref_id)
        if not recipe:
            return None, None, None, None
        value = await crafts_db.recipe_value(ref_id)
        label = f"🧪 «{recipe['name']}»"
        return None, None, label, value

    if card_type == "base":
        card = await cards_db.get_card(ref_id)
        if not card:
            return None, None, None, None
        return card, 1.0, card["name"], card["current_rate"]

    if card_type == "upgrade":
        variant = await cards_db.get_variant(ref_id)
        if not variant:
            return None, None, None, None
        release = await cards_db.get_release(variant["release_id"])
        if not release:
            return None, None, None, None
        card = await cards_db.get_card(release["base_card_id"])
        if not card:
            return None, None, None, None
        mult = RARITY_MULTIPLIERS.get(variant["rarity"], 1.0)
        label = f"{RARITY_NAMES.get(variant['rarity'], variant['rarity'])} «{variant['name']}»"
        return card, mult, label, card["current_rate"] * mult

    return None, None, None, None


# ============================================================
#   АВТОПРОДАЖА КАРТ БОТУ ПО ТЕКУЩЕМУ КУРСУ (обычные И улучшенные)
# ============================================================

@router.callback_query(F.data.startswith("autosell_start:"))
async def cb_autosell_start(callback: CallbackQuery, state: FSMContext):
    _, card_type, ref_id = callback.data.split(":")
    ref_id = int(ref_id)
    owned = await inv_db.count_owned(callback.from_user.id, card_type, ref_id)
    if owned == 0:
        await callback.answer("У вас нет таких карт", show_alert=True)
        return

    held, held_until = await holdings_db.is_locked(callback.from_user.id, card_type, ref_id)
    if held:
        await callback.answer(f"🔒 Вы захолдили эти карты до {held_until} UTC — снимите холд, чтобы продать", show_alert=True)
        return

    base_card, mult, label, unit_value = await _resolve_unit(card_type, ref_id)
    if label is None:
        await callback.answer("❌ Карта не найдена", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AutoSell.quantity)
    await state.update_data(card_type=card_type, ref_id=ref_id)
    await callback.message.answer(
        f"📉 Продажа карты «<b>{label}</b>» боту по текущему курсу (⭐ {unit_value:.2f}/шт).\n"
        f"У вас есть: <b>{owned} шт.</b>\n\n"
        f"Сколько продать? Введите число (или «все»):",
        parse_mode="HTML",
    )


@router.message(AutoSell.quantity)
async def process_autosell_qty(message: Message, state: FSMContext):
    data = await state.get_data()
    card_type, ref_id = data["card_type"], data["ref_id"]
    owned = await inv_db.count_owned(message.from_user.id, card_type, ref_id)

    text = message.text.strip().lower()
    if text in ("все", "всё", "all"):
        qty = owned
    elif text.isdigit():
        qty = int(text)
    else:
        await message.answer("❗ Введите целое число или «все».")
        return

    if qty <= 0 or qty > owned:
        await message.answer(f"❗ Введите число от 1 до {owned}.")
        return

    base_card, mult, label, unit_value = await _resolve_unit(card_type, ref_id)
    if label is None:
        await message.answer("❌ Карта не найдена.")
        await state.clear()
        return

    if base_card is None:
        # crafted-карта: фиксированная цена, без проседания курса
        gross = unit_value * qty
        final_base_rate = None
        base_card_id = None
    else:
        rate = base_card["current_rate"]
        gross = 0.0
        for _ in range(qty):
            gross += rate * mult
            rate = pricing.apply_trade(rate, rate, "sell", base_card["base_price"])
        final_base_rate = rate
        base_card_id = base_card["card_id"]

    commission = round(gross * MARKET_COMMISSION, 2)
    net = round(gross - commission, 2)

    await state.update_data(qty=qty, gross=gross, commission=commission, net=net,
                             final_base_rate=final_base_rate, base_card_id=base_card_id)
    await state.set_state(AutoSell.confirm)
    await message.answer(
        f"📉 Продажа {qty} шт. «{label}»:\n\n"
        f"Выручка: ⭐ {gross:.2f}\n"
        f"Комиссия биржи ({MARKET_COMMISSION*100:.0f}%): -⭐ {commission:.2f}\n"
        f"<b>Вы получите: ⭐ {net:.2f}</b>",
        parse_mode="HTML",
        reply_markup=confirm_kb("autosell_confirm"),
    )


@router.callback_query(F.data == "autosell_confirm", AutoSell.confirm)
async def cb_autosell_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    card_type, ref_id, qty = data["card_type"], data["ref_id"], data["qty"]

    owned = await inv_db.count_owned(callback.from_user.id, card_type, ref_id)
    if owned < qty:
        await callback.answer("❌ У вас изменилось количество карт, попробуйте заново", show_alert=True)
        return

    await inv_db.take_units(callback.from_user.id, card_type, ref_id, qty)
    await users_db.change_balance(callback.from_user.id, data["net"], "sell_card",
                                   f"Продажа {qty} карт ({card_type} {ref_id})")
    await users_db.change_balance(ADMIN_IDS[0], data["commission"], "market_commission",
                                   f"Комиссия с продажи {qty} карт ({card_type} {ref_id})")
    if data.get("base_card_id") is not None:
        await cards_db.update_card_rate(data["base_card_id"], data["final_base_rate"])

    await callback.answer("✅ Продано!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ <b>Продажа завершена</b>\n━━━━━━━━━━━━━━━━\n💰 Получено: <b>⭐ {data['net']:.2f}</b> на баланс.",
        parse_mode="HTML",
    )


# ============================================================
#   УЛУЧШЕНИЕ КАРТ (ГАЧА)
# ============================================================

@router.callback_query(F.data.startswith("upgrade_start:"))
async def cb_upgrade_start(callback: CallbackQuery, state: FSMContext):
    card_id = int(callback.data.split(":")[1])
    card = await cards_db.get_card(card_id)
    release = await cards_db.get_active_release_for_card(card_id)
    if not release:
        await callback.answer("Сейчас нет активных улучшений для этой карты", show_alert=True)
        return
    owned = await inv_db.count_owned(callback.from_user.id, "base", card_id)
    if owned == 0:
        await callback.answer("У вас нет обычных карт этого вида для улучшения", show_alert=True)
        return

    await callback.answer()
    price = cards_db.current_pull_price(release)
    card = await cards_db.get_card(card_id)
    await state.set_state(UpgradeCards.quantity)
    await state.update_data(card_id=card_id, release_id=release["release_id"])
    await callback.message.answer(
        f"⚗️ Улучшение карты «<b>{card['name']}</b>»\n\n"
        f"Цена попытки сейчас: <b>⭐ {price:.2f}</b> "
        f"(за 1 обычную карту + звёзды)\n"
        f"У вас обычных карт: {owned} шт.\n\n"
        f"Сколько попыток провести? Введите число:",
        parse_mode="HTML",
    )


@router.message(UpgradeCards.quantity)
async def process_upgrade_qty(message: Message, state: FSMContext):
    data = await state.get_data()
    card_id, release_id = data["card_id"], data["release_id"]

    if not message.text or not message.text.strip().isdigit():
        await message.answer("❗ Введите целое число попыток.")
        return
    qty = int(message.text.strip())

    owned = await inv_db.count_owned(message.from_user.id, "base", card_id)
    if qty <= 0 or qty > owned:
        await message.answer(f"❗ Введите число от 1 до {owned}.")
        return

    release = await cards_db.get_release(release_id)
    if not release or release["is_paused"]:
        await message.answer("⏸ Улучшения для этой карты сейчас приостановлены администратором.")
        await state.clear()
        return

    price = cards_db.current_pull_price(release)
    total_cost = round(price * qty, 2)
    user = await users_db.get_user(message.from_user.id)
    if user["balance"] < total_cost:
        await message.answer(f"❗ Недостаточно звёзд. Нужно ⭐ {total_cost:.2f}, у вас ⭐ {user['balance']:.2f}.")
        return

    await state.update_data(qty=qty, price=price, total_cost=total_cost)
    await state.set_state(UpgradeCards.confirm)
    await message.answer(
        f"⚗️ Подтвердите: {qty} попыт{'ка' if qty==1 else ('ки' if qty<5 else 'ок')} улучшения.\n"
        f"Спишется {qty} обычных карт + ⭐ {total_cost:.2f}.",
        reply_markup=confirm_kb("upgrade_confirm"),
    )


@router.callback_query(F.data == "upgrade_confirm", UpgradeCards.confirm)
async def cb_upgrade_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    card_id, release_id, qty = data["card_id"], data["release_id"], data["qty"]

    release = await cards_db.get_release(release_id)
    if not release or release["is_paused"]:
        await callback.answer("⏸ Улучшения были приостановлены", show_alert=True)
        return

    owned = await inv_db.count_owned(callback.from_user.id, "base", card_id)
    user = await users_db.get_user(callback.from_user.id)
    if owned < qty or user["balance"] < data["total_cost"]:
        await callback.answer("❌ Недостаточно карт или звёзд, попробуйте заново", show_alert=True)
        return

    await callback.answer("✨ Улучшаем...")
    await callback.message.edit_reply_markup(reply_markup=None)

    await inv_db.take_units(callback.from_user.id, "base", card_id, qty)
    await users_db.change_balance(callback.from_user.id, -data["total_cost"], "upgrade_fee",
                                   f"Улучшение {qty} карт (release {release_id})")
    await users_db.change_balance(ADMIN_IDS[0], data["total_cost"], "upgrade_revenue",
                                   f"Доход с улучшений {qty} карт (release {release_id})")

    card = await cards_db.get_card(card_id)
    results = {}
    fails = 0
    for _ in range(qty):
        variant = await cards_db.roll_variant_for_release(release_id)
        if not variant:
            fails += 1
            continue
        value = cards_db.variant_value(card["current_rate"], variant["rarity"])
        await inv_db.add_to_inventory(callback.from_user.id, "upgrade", variant["variant_id"], value)
        results[variant["rarity"]] = results.get(variant["rarity"], 0) + 1

    if fails:
        refund = round(data["price"] * fails, 2)
        await users_db.change_balance(callback.from_user.id, refund, "upgrade_refund",
                                       f"Возврат за {fails} неудачных попыток")

    if results:
        lines = "\n".join(f"• {RARITY_NAMES.get(r, r)} × {c}" for r, c in results.items())
        text = f"🎉 <b>Результаты улучшения:</b>\n\n{lines}"
    else:
        text = "😔 В этот раз ничего не выпало, звёзды за неудачные попытки возвращены."
    await callback.message.answer(text, parse_mode="HTML")


# ============================================================
#   ПЕРЕДАЧА УЛУЧШЕННЫХ КАРТ ДРУГОМУ ПОЛЬЗОВАТЕЛЮ
# ============================================================

@router.callback_query(F.data.startswith("gift_start:"))
async def cb_gift_start(callback: CallbackQuery, state: FSMContext):
    variant_id = int(callback.data.split(":")[1])
    owned = await inv_db.count_owned(callback.from_user.id, "upgrade", variant_id)
    if owned == 0:
        await callback.answer("У вас нет таких карт", show_alert=True)
        return
    held, held_until = await holdings_db.is_locked(callback.from_user.id, "upgrade", variant_id)
    if held:
        await callback.answer(f"🔒 Вы захолдили эти карты до {held_until} UTC — снимите холд, чтобы передать", show_alert=True)
        return

    await callback.answer()
    await state.set_state(TransferCard.quantity)
    await state.update_data(variant_id=variant_id)
    await callback.message.answer(
        f"🎁 Передача карты другому пользователю.\nУ вас есть: <b>{owned} шт.</b>\n\n"
        f"Сколько карт передать? Введите число (или «все»):",
        parse_mode="HTML",
    )


@router.message(TransferCard.quantity)
async def process_gift_qty(message: Message, state: FSMContext):
    data = await state.get_data()
    variant_id = data["variant_id"]
    owned = await inv_db.count_owned(message.from_user.id, "upgrade", variant_id)

    text = message.text.strip().lower()
    if text in ("все", "всё", "all"):
        qty = owned
    elif text.isdigit():
        qty = int(text)
    else:
        await message.answer("❗ Введите целое число или «все».")
        return

    if qty <= 0 or qty > owned:
        await message.answer(f"❗ Введите число от 1 до {owned}.")
        return

    await state.update_data(qty=qty)
    await state.set_state(TransferCard.target)
    await message.answer("👤 Укажите ID или @username получателя (он должен хотя бы раз запустить бота):")


@router.message(TransferCard.target)
async def process_gift_target(message: Message, state: FSMContext):
    recipient = await users_db.resolve_user(message.text.strip())
    if not recipient:
        await message.answer("❗ Пользователь не найден. Попробуйте ещё раз или отправьте ID/@username.")
        return
    if recipient["user_id"] == message.from_user.id:
        await message.answer("❗ Нельзя передать карту самому себе.")
        return

    data = await state.get_data()
    variant = await cards_db.get_variant(data["variant_id"])
    label = variant["name"] if variant else "карта"

    await state.update_data(target_id=recipient["user_id"], target_label=recipient["username"] or recipient["user_id"])
    await state.set_state(TransferCard.confirm)
    await message.answer(
        f"🎁 Подтвердите передачу: {data['qty']} шт. «{label}» пользователю "
        f"@{recipient['username'] or recipient['user_id']}.\nПередача бесплатна, отменить её будет нельзя.",
        reply_markup=confirm_kb("gift_confirm"),
    )


@router.callback_query(F.data == "gift_confirm", TransferCard.confirm)
async def cb_gift_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    variant_id, qty, target_id = data["variant_id"], data["qty"], data["target_id"]

    owned = await inv_db.count_owned(callback.from_user.id, "upgrade", variant_id)
    if owned < qty:
        await callback.answer("❌ У вас изменилось количество карт, попробуйте заново", show_alert=True)
        return

    await inv_db.take_units(callback.from_user.id, "upgrade", variant_id, qty)

    variant = await cards_db.get_variant(variant_id)
    release = await cards_db.get_release(variant["release_id"]) if variant else None
    base_card = await cards_db.get_card(release["base_card_id"]) if release else None
    unit_value = cards_db.variant_value(base_card["current_rate"], variant["rarity"]) if base_card else 0.0
    await inv_db.add_bulk(target_id, "upgrade", variant_id, unit_value, count=qty)

    await callback.answer("🎁 Передано!")
    await callback.message.edit_reply_markup(reply_markup=None)
    label = variant["name"] if variant else "карта"
    await callback.message.answer(f"✅ Вы передали {qty} шт. «{label}» пользователю.")
    try:
        await bot.send_message(
            target_id,
            f"🎁 Вам передали {qty} шт. карты «{label}» от @{callback.from_user.username or callback.from_user.id}!",
        )
    except Exception:
        pass

