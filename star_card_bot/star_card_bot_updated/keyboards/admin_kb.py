from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_panel_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🃏 Создать карту"), KeyboardButton(text="⚗️ Выпустить улучшения")],
        [KeyboardButton(text="⏯ Управление улучшениями"), KeyboardButton(text="🧪 Создать крафт")],
        [KeyboardButton(text="⏯ Управление крафтом"), KeyboardButton(text="🎛 Кнопка крафта в меню")],
        [KeyboardButton(text="🗳 Заявки на карты"), KeyboardButton(text="💰 Изменить баланс")],
        [KeyboardButton(text="💱 Канал для выводов"), KeyboardButton(text="🎫 Создать чек")],
        [KeyboardButton(text="🛡 Модераторы"), KeyboardButton(text="📢 Каналы")],
        [KeyboardButton(text="🚫 Бан/Разбан"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="⬅️ Главное меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def moderator_panel_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="💸 Заявки на вывод"), KeyboardButton(text="🎫 Обращения")],
        [KeyboardButton(text="⬅️ Главное меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def rarity_pick_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔵 Редкая", callback_data="rarity:rare")
    b.button(text="🟣 Эпическая", callback_data="rarity:epic")
    b.button(text="🟠 Мифическая", callback_data="rarity:mythic")
    b.button(text="🟡 Легендарная", callback_data="rarity:legendary")
    b.adjust(2, 2)
    return b.as_markup()


def stock_choice_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="♾ Без ограничений", callback_data="stock:unlimited")
    b.button(text="🔢 Указать количество", callback_data="stock:limited")
    b.adjust(1)
    return b.as_markup()


def card_review_kb(card_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Одобрить", callback_data=f"card_approve:{card_id}")
    b.button(text="❌ Отклонить", callback_data=f"card_reject:{card_id}")
    b.adjust(2)
    return b.as_markup()


def base_cards_pick_kb(cards) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in cards:
        b.row(InlineKeyboardButton(text=f"{c['name']} (⭐ {c['current_rate']:.2f})",
                                    callback_data=f"pick_base:{c['card_id']}"))
    return b.as_markup()


def release_draft_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить ещё вариант", callback_data="add_variant")
    b.button(text="✅ Готово, опубликовать", callback_data="publish_release")
    b.button(text="❌ Отменить всё", callback_data="discard_release")
    b.adjust(1)
    return b.as_markup()


def releases_manage_kb(releases_with_cards) -> InlineKeyboardMarkup:
    """releases_with_cards: список (release, card_name, is_paused)"""
    b = InlineKeyboardBuilder()
    for rel in releases_with_cards:
        icon = "▶️ Возобновить" if rel["is_paused"] else "⏸ Пауза"
        b.row(InlineKeyboardButton(
            text=f"{rel['card_name']} — релиз #{rel['release_id']} ({icon})",
            callback_data=f"toggle_release:{rel['release_id']}",
        ))
    return b.as_markup()


def craft_menu_toggle_kb(visible: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if visible:
        b.button(text="🙈 Скрыть кнопку «Крафт» из меню", callback_data="craftmenu_hide")
    else:
        b.button(text="👁 Показать кнопку «Крафт» в меню", callback_data="craftmenu_show")
    b.adjust(1)
    return b.as_markup()


def withdraw_review_kb(request_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Одобрить", callback_data=f"wd_approve:{request_id}")
    b.button(text="❌ Отклонить", callback_data=f"wd_decline:{request_id}")
    b.adjust(2)
    return b.as_markup()


def ticket_review_kb(ticket_id: int, claimed: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not claimed:
        b.button(text="✋ Взять в работу", callback_data=f"claim_ticket:{ticket_id}")
    b.button(text="✍️ Ответить", callback_data=f"reply_ticket:{ticket_id}")
    b.button(text="✅ Закрыть", callback_data=f"close_ticket_staff:{ticket_id}")
    b.adjust(1)
    return b.as_markup()


def channels_manage_kb(channels) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.row(InlineKeyboardButton(text=f"❌ {ch['title']}", callback_data=f"del_channel:{ch['channel_id']}"))
    b.row(InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel"))
    return b.as_markup()


def moderators_manage_kb(mods) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for m in mods:
        label = f"❌ {m['username'] or m['user_id']}"
        b.row(InlineKeyboardButton(text=label, callback_data=f"del_mod:{m['user_id']}"))
    b.row(InlineKeyboardButton(text="➕ Назначить модератора", callback_data="add_mod"))
    return b.as_markup()
