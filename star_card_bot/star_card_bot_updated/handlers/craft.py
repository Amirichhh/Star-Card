from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from database import crafts as crafts_db, inventory as inv_db, cards as cards_db
from services.valuation import resolve_card_info
from services.image import render_card_image
from keyboards.craft_kb import craft_list_kb, craft_view_kb

router = Router(name="craft")


@router.message(F.text == "🧪 Крафт")
@router.message(F.text == "/craft")
async def craft_menu(message: Message):
    recipes = await crafts_db.list_available_recipes()
    if not recipes:
        await message.answer("😔 Пока нет доступных рецептов крафта.")
        return
    await message.answer(
        "🧪 <b>Крафт карт</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Вкладываете конкретные карты (в том числе улучшенные) — бесплатно, но с риском: "
        "если крафт не удастся, все вложенные карты сгорят без остатка.\n\n"
        "👇 Выберите рецепт:",
        parse_mode="HTML",
        reply_markup=craft_list_kb(recipes),
    )


@router.callback_query(F.data == "craft_menu")
async def cb_craft_menu(callback: CallbackQuery):
    await callback.answer()
    recipes = await crafts_db.list_available_recipes()
    if not recipes:
        await callback.message.answer("😔 Пока нет доступных рецептов крафта.")
        return
    await callback.message.answer("🧪 <b>Крафт карт</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n👇 Выберите рецепт:", parse_mode="HTML",
                                   reply_markup=craft_list_kb(recipes))


@router.callback_query(F.data.startswith("craft_view:"))
async def cb_craft_view(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    recipe_id = int(callback.data.split(":")[1])
    recipe = await crafts_db.get_recipe(recipe_id)
    if not recipe or recipe["is_paused"] or recipe["is_draft"]:
        await callback.message.answer("⏸ Этот рецепт сейчас недоступен.")
        return

    ingredients = await crafts_db.list_ingredients(recipe_id)
    lines = [f"🧪 <b>{recipe['name']}</b>", "━━━━━━━━━━━━━━━━",
             f"🎲 Шанс успеха: <b>{recipe['success_chance']*100:.0f}%</b>",
             "⚠️ При неудаче все вложенные карты сгорают безвозвратно!\n", "<b>📥 Нужно вложить:</b>"]
    eligible = True
    for ing in ingredients:
        info = await resolve_card_info(ing["card_type"], ing["card_ref_id"])
        owned = await inv_db.count_owned(callback.from_user.id, ing["card_type"], ing["card_ref_id"])
        label = info["label"] if info else "❓ карта удалена"
        ok = info is not None and owned >= ing["quantity"]
        if not ok:
            eligible = False
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} {label} — нужно {ing['quantity']}, у вас {owned}")

    result_value = await crafts_db.recipe_value(recipe_id)
    lines.append(f"\n💎 Ценность карты-результата: <b>⭐ {result_value:.2f}</b>")
    caption = "\n".join(lines)

    photo = await render_card_image(bot, recipe["photo_file_id"], recipe["name"], result_value)
    kb = craft_view_kb(recipe_id, eligible)
    if photo:
        await callback.message.answer_photo(photo, caption=caption, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.answer(caption, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("craft_do:"))
async def cb_craft_do(callback: CallbackQuery):
    recipe_id = int(callback.data.split(":")[1])
    recipe = await crafts_db.get_recipe(recipe_id)
    if not recipe or recipe["is_paused"] or recipe["is_draft"]:
        await callback.answer("⏸ Этот рецепт сейчас недоступен", show_alert=True)
        return

    ingredients = await crafts_db.list_ingredients(recipe_id)
    for ing in ingredients:
        owned = await inv_db.count_owned(callback.from_user.id, ing["card_type"], ing["card_ref_id"])
        if owned < ing["quantity"]:
            await callback.answer("❌ У вас не хватает ингредиентов, попробуйте заново", show_alert=True)
            return

    await callback.answer("🧪 Крафтим...")
    await callback.message.edit_reply_markup(reply_markup=None)

    # ингредиенты сгорают в любом случае, независимо от результата
    for ing in ingredients:
        await inv_db.take_units(callback.from_user.id, ing["card_type"], ing["card_ref_id"], ing["quantity"])

    success = crafts_db.roll_success(recipe["success_chance"])
    if success:
        value = await crafts_db.recipe_value(recipe_id)
        await inv_db.add_to_inventory(callback.from_user.id, "craft", recipe_id, value)
        await callback.message.answer(
            f"🎉 <b>Крафт удался!</b>\n━━━━━━━━━━━━━━━━\n"
            f"Вы получили «<b>{recipe['name']}</b>» (⭐ {value:.2f}).",
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            f"💥 <b>Крафт не удался!</b>\nВсе вложенные карты потеряны. Повезёт в следующий раз.",
            parse_mode="HTML",
        )
