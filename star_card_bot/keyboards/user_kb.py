from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import RARITY_NAMES


def main_menu_kb(is_staff: bool = False, is_admin: bool = False, show_craft: bool = True) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🛍 Магазин карт")],
        [KeyboardButton(text="📈 Биржа"), KeyboardButton(text="⭐ Пополнить баланс")],
        [KeyboardButton(text="💸 Вывод звёзд"), KeyboardButton(text="💱 Перевести звёзды")],
    ]
    if show_craft:
        rows.append([KeyboardButton(text="🧪 Крафт"), KeyboardButton(text="🖌 Создать свою карту")])
    else:
        rows.append([KeyboardButton(text="🖌 Создать свою карту")])
    rows.append([KeyboardButton(text="🆘 Поддержка"), KeyboardButton(text="ℹ️ Помощь")])
    if is_staff:
        rows.append([KeyboardButton(text="🛠 Панель модератора")])
    if is_admin:
        rows.append([KeyboardButton(text="👑 Панель администратора")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def subscribe_kb(channels) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        url = ch["url"] or f"https://t.me/{str(ch['chat_id']).lstrip('@')}"
        b.row(InlineKeyboardButton(text=f"📢 {ch['title']}", url=url))
    b.row(InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription"))
    return b.as_markup()


def topup_amounts_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for amount in (25, 50, 100, 250, 500, 1000):
        b.button(text=f"⭐ {amount}", callback_data=f"topup:{amount}")
    b.button(text="✏️ Своя сумма", callback_data="topup:custom")
    b.adjust(3, 3, 1)
    return b.as_markup()


# ---------------- МАГАЗИН / БИРЖА (список карт) ----------------

def cards_list_kb(cards, page: int, has_next: bool, prefix: str, with_search: bool = False) -> InlineKeyboardMarkup:
    """Универсальная пагинированная клавиатура списка карт.
    prefix используется в callback_data для страниц (shop / market)."""
    b = InlineKeyboardBuilder()
    for c in cards:
        from database.cards import day_change_percent
        chg = day_change_percent(c)
        arrow = "🟢+" if chg >= 0 else "🔴"
        b.row(InlineKeyboardButton(
            text=f"{c['name']} — ⭐ {c['current_rate']:.2f} ({arrow}{chg:.1f}%)",
            callback_data=f"card_view:{c['card_id']}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_page:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_page:{page+1}"))
    if nav:
        b.row(*nav)
    if with_search:
        b.row(InlineKeyboardButton(text="🔍 Поиск по названию", callback_data="shop_search"))
    return b.as_markup()


def card_view_kb(card_id: int, price: float, has_release: bool,
                  in_stock: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not in_stock:
        b.button(text="❌ Раскуплено", callback_data="noop")
    else:
        b.button(text=f"💳 Купить за ⭐ {price:.2f}", callback_data=f"buy_base:{card_id}")
    if has_release:
        b.button(text="⚗️ Улучшить мои карты", callback_data=f"upgrade_start:{card_id}")
    b.button(text="📉 Продать мои карты (авто)", callback_data=f"autosell_start:base:{card_id}")
    b.adjust(1)
    return b.as_markup()


# ---------------- ПРОФИЛЬ ----------------

def profile_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗂 Мои карты", callback_data="my_cards")
    b.button(text="🖌 Мои созданные карты", callback_data="my_created_cards")
    b.button(text="📜 Мои заявки на вывод", callback_data="my_withdrawals")
    b.adjust(1)
    return b.as_markup()


def my_cards_kb(groups) -> InlineKeyboardMarkup:
    """groups: список dict с полями label, card_type, ref_id"""
    b = InlineKeyboardBuilder()
    for g in groups:
        b.row(InlineKeyboardButton(
            text=g["label"],
            callback_data=f"group_view:{g['card_type']}:{g['ref_id']}",
        ))
    b.row(InlineKeyboardButton(text="⬅️ Профиль", callback_data="back_profile"))
    return b.as_markup()


def group_view_kb(card_type: str, ref_id: int, has_release: bool,
                   held: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if held:
        # Пока холд активен — снять его раньше срока НЕЛЬЗЯ никак,
        # кнопка неактивна и служит только индикатором.
        b.button(text="🔒 Холд активен до срока", callback_data="noop")
    else:
        b.button(text="🔒 Захолдить (не продавать)", callback_data=f"hold_start:{card_type}:{ref_id}")
        b.button(text="📉 Продать несколько по курсу", callback_data=f"autosell_start:{card_type}:{ref_id}")
    if card_type == "base":
        if has_release:
            b.button(text="⚗️ Улучшить несколько карт", callback_data=f"upgrade_start:{ref_id}")
    elif card_type == "upgrade" and not held:
        b.button(text="🎁 Передать другому пользователю", callback_data=f"gift_start:{ref_id}")
    b.button(text="⬅️ Мои карты", callback_data="my_cards")
    b.adjust(1)
    return b.as_markup()


def rarity_variants_kb(rarities) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rarities:
        b.row(InlineKeyboardButton(text=RARITY_NAMES.get(r, r), callback_data="noop"))
    return b.as_markup()


def confirm_kb(yes_cb: str, no_cb: str = "cancel_action") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=yes_cb)
    b.button(text="❌ Отмена", callback_data=no_cb)
    b.adjust(2)
    return b.as_markup()


def ticket_user_kb(ticket_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Закрыть обращение", callback_data=f"close_ticket:{ticket_id}")
    return b.as_markup()


# ---------------- СВОИ СОЗДАННЫЕ КАРТЫ ----------------

def my_created_cards_kb(cards) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
    for c in cards:
        icon = status_icon.get(c["approval_status"], "•")
        b.row(InlineKeyboardButton(text=f"{icon} {c['name']}", callback_data=f"my_created_card:{c['card_id']}"))
    return b.as_markup()


def created_card_status_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Мои созданные карты", callback_data="my_created_cards")
    return b.as_markup()
