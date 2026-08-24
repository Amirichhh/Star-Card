from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import RARITY_NAMES


def ingredient_type_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🃏 Обычная карта", callback_data="ingtype:base")
    b.button(text="⚗️ Конкретная улучшенная карта", callback_data="ingtype:upgrade")
    b.adjust(1)
    return b.as_markup()


def pick_base_kb(cards) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in cards:
        b.row(InlineKeyboardButton(text=f"{c['name']} (⭐ {c['current_rate']:.2f})",
                                    callback_data=f"ingpick:base:{c['card_id']}"))
    return b.as_markup()


def pick_variant_kb(variants) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for v in variants:
        rarity_label = RARITY_NAMES.get(v["rarity"], v["rarity"])
        b.row(InlineKeyboardButton(
            text=f"{rarity_label} «{v['name']}» ({v['base_name']})",
            callback_data=f"ingpick:upgrade:{v['variant_id']}",
        ))
    return b.as_markup()


def craft_draft_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить ещё ингредиент", callback_data="add_ingredient")
    b.button(text="✅ Готово, опубликовать", callback_data="publish_craft")
    b.button(text="❌ Отменить всё", callback_data="discard_craft")
    b.adjust(1)
    return b.as_markup()


def crafts_manage_kb(recipes) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in recipes:
        icon = "▶️ Возобновить" if r["is_paused"] else "⏸ Пауза"
        b.row(InlineKeyboardButton(
            text=f"«{r['name']}» ({r['success_chance']*100:.0f}% успех) — {icon}",
            callback_data=f"toggle_craft:{r['recipe_id']}",
        ))
    return b.as_markup()


# ---------------- ПОЛЬЗОВАТЕЛЬСКАЯ ВИТРИНА КРАФТА ----------------

def craft_list_kb(recipes) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in recipes:
        b.row(InlineKeyboardButton(
            text=f"🧪 «{r['name']}» (шанс {r['success_chance']*100:.0f}%)",
            callback_data=f"craft_view:{r['recipe_id']}",
        ))
    return b.as_markup()


def craft_view_kb(recipe_id: int, eligible: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if eligible:
        b.button(text="🧪 Скрафтить (бесплатно)", callback_data=f"craft_do:{recipe_id}")
    else:
        b.button(text="❌ Не хватает ингредиентов", callback_data="noop")
    b.button(text="⬅️ К списку крафтов", callback_data="craft_menu")
    b.adjust(1)
    return b.as_markup()
