from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import cards as cards_db, crafts as crafts_db
from config import RARITY_NAMES
from states import CreateCraft
from keyboards.craft_kb import (
    ingredient_type_kb, pick_base_kb, pick_variant_kb,
    craft_draft_kb, crafts_manage_kb,
)
from keyboards.user_kb import confirm_kb
from filters import IsAdmin

router = Router(name="craft_admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ============================================================
#   СОЗДАНИЕ РЕЦЕПТА КРАФТА
# ============================================================

@router.message(F.text == "🧪 Создать крафт")
async def create_craft_start(message: Message, state: FSMContext):
    await state.set_state(CreateCraft.name)
    await message.answer(
        "🧪 <b>Создание рецепта крафта</b>\n━━━━━━━━━━━━━━━━\n"
        "Ингредиентами могут быть ЛЮБЫЕ карты — обычные или конкретные улучшенные. "
        "Крафт бесплатный, но при неудаче все вложенные карты сгорают.\n\n"
        "✏️ Введите название карты-результата:",
        parse_mode="HTML",
    )


@router.message(CreateCraft.name)
async def create_craft_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CreateCraft.photo)
    await message.answer("📸 Пришлите фото карты-результата:")


@router.message(CreateCraft.photo, F.photo)
async def create_craft_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(CreateCraft.success_chance)
    await message.answer("🎲 Укажите шанс успеха крафта в процентах (например 25):")


@router.message(CreateCraft.photo)
async def create_craft_photo_invalid(message: Message):
    await message.answer("❗ Пришлите именно фото.")


@router.message(CreateCraft.success_chance)
async def create_craft_chance(message: Message, state: FSMContext):
    text = message.text.strip().replace("%", "")
    if not text.replace(".", "", 1).isdigit():
        await message.answer("❗ Введите число от 1 до 100.")
        return
    chance = float(text)
    if not (0 < chance <= 100):
        await message.answer("❗ Введите число от 1 до 100.")
        return

    data = await state.get_data()
    recipe_id = await crafts_db.create_recipe_draft(
        data["name"], data["photo_file_id"], chance / 100, message.from_user.id,
    )
    await state.update_data(success_chance=chance / 100, ingredients=[], recipe_id=recipe_id)
    await state.set_state(CreateCraft.ingredient_type)
    await message.answer(
        f"🎲 Шанс успеха: {chance:.0f}%\n\nТеперь добавьте ингредиенты (карты, которые нужно вложить).\n"
        f"Какой тип карты добавить первым?",
        reply_markup=ingredient_type_kb(),
    )


@router.callback_query(F.data.startswith("ingtype:"), CreateCraft.ingredient_type)
async def create_craft_ingredient_type(callback: CallbackQuery, state: FSMContext):
    ing_type = callback.data.split(":")[1]
    await state.update_data(current_ing_type=ing_type)
    await state.set_state(CreateCraft.ingredient_pick)
    await callback.answer()

    if ing_type == "base":
        items = await cards_db.list_active_cards(limit=200)
        if not items:
            await callback.message.answer("❗ Нет доступных обычных карт. Выберите другой тип.")
            await state.set_state(CreateCraft.ingredient_type)
            return
        await callback.message.answer("Выберите обычную карту-ингредиент:", reply_markup=pick_base_kb(items))
    elif ing_type == "upgrade":
        items = await cards_db.list_all_published_variants()
        if not items:
            await callback.message.answer("❗ Пока нет опубликованных улучшенных карт. Выберите другой тип.")
            await state.set_state(CreateCraft.ingredient_type)
            return
        await callback.message.answer("Выберите конкретную улучшенную карту-ингредиент:",
                                       reply_markup=pick_variant_kb(items))


@router.callback_query(F.data.startswith("ingpick:"), CreateCraft.ingredient_pick)
async def create_craft_ingredient_pick(callback: CallbackQuery, state: FSMContext):
    _, ing_type, ref_id = callback.data.split(":")
    await state.update_data(current_ing_ref_id=int(ref_id))
    await state.set_state(CreateCraft.ingredient_qty)
    await callback.answer()
    await callback.message.answer("🔢 Сколько штук этой карты нужно вложить? Введите число:")


@router.message(CreateCraft.ingredient_qty)
async def create_craft_ingredient_qty(message: Message, state: FSMContext):
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Введите целое число больше 0.")
        return
    qty = int(message.text.strip())
    data = await state.get_data()

    from services.valuation import resolve_card_info
    info = await resolve_card_info(data["current_ing_type"], data["current_ing_ref_id"])
    label = info["label"] if info else "❓"

    await crafts_db.add_ingredient(data["recipe_id"], data["current_ing_type"], data["current_ing_ref_id"], qty)
    ingredients = data.get("ingredients", [])
    ingredients.append({"label": label, "qty": qty})
    await state.update_data(ingredients=ingredients)
    await state.set_state(CreateCraft.confirm)

    summary = "\n".join(f"• {i['qty']}× {i['label']}" for i in ingredients)
    await message.answer(
        f"✅ Ингредиент добавлен!\n\n<b>Текущий состав рецепта «{data['name']}»:</b>\n{summary}\n\n"
        f"Добавить ещё ингредиент или опубликовать рецепт?",
        parse_mode="HTML",
        reply_markup=craft_draft_kb(),
    )


@router.callback_query(F.data == "add_ingredient", CreateCraft.confirm)
async def create_craft_add_more(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateCraft.ingredient_type)
    await callback.answer()
    await callback.message.answer("Какой тип карты добавить?", reply_markup=ingredient_type_kb())


@router.callback_query(F.data == "discard_craft", CreateCraft.confirm)
async def create_craft_discard(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await crafts_db.discard_recipe(data["recipe_id"])
    await state.clear()
    await callback.answer("❌ Отменено")
    await callback.message.answer("❌ Черновик рецепта крафта удалён.")


@router.callback_query(F.data == "publish_craft", CreateCraft.confirm)
async def create_craft_publish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("ingredients"):
        await callback.answer("Добавьте хотя бы один ингредиент", show_alert=True)
        return
    await crafts_db.publish_recipe(data["recipe_id"])
    await state.clear()
    await callback.answer("🚀 Опубликовано!")
    await callback.message.answer(
        f"🚀 Крафт «{data['name']}» запущен! Пользователи теперь могут его пробовать "
        f"(шанс успеха {data['success_chance']*100:.0f}%)."
    )


# ---------------- ПАУЗА / ВОЗОБНОВЛЕНИЕ ----------------

@router.message(F.text == "⏯ Управление крафтом")
async def manage_crafts(message: Message):
    recipes = await crafts_db.list_all_published_recipes()
    if not recipes:
        await message.answer("Пока нет опубликованных рецептов крафта.")
        return
    await message.answer("⏯ Рецепты крафта:", reply_markup=crafts_manage_kb(recipes))


@router.callback_query(F.data.startswith("toggle_craft:"))
async def cb_toggle_craft(callback: CallbackQuery):
    recipe_id = int(callback.data.split(":")[1])
    recipe = await crafts_db.get_recipe(recipe_id)
    if not recipe:
        await callback.answer("Не найдено", show_alert=True)
        return
    await crafts_db.set_recipe_paused(recipe_id, not recipe["is_paused"])
    await callback.answer("Готово")
    recipes = await crafts_db.list_all_published_recipes()
    await callback.message.edit_reply_markup(reply_markup=crafts_manage_kb(recipes))
