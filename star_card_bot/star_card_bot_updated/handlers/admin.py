from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import (
    cards as cards_db, users as users_db, channels as channels_db,
    checks as checks_db, withdraw as wd_db, tickets as tickets_db,
)
from database.db import get_setting, set_setting
from config import (
    RARITY_NAMES, RARITY_ORDER, CUSTOM_CARD_APPROVAL_FEE,
    WITHDRAW_LOG_CHANNEL_SETTING_KEY, CRAFT_MENU_SETTING_KEY, ADMIN_IDS,
)
from states import (
    CreateCard, CreateRelease, SetBalance, ManageModerators, ManageChannels,
    BanUser, UnbanUser, CreateCheck, SetWithdrawChannel,
)
from keyboards.admin_kb import (
    admin_panel_kb, rarity_pick_kb, base_cards_pick_kb, release_draft_kb,
    releases_manage_kb, channels_manage_kb, moderators_manage_kb,
    craft_menu_toggle_kb, stock_choice_kb, card_review_kb,
)
from keyboards.user_kb import confirm_kb
from filters import IsAdmin

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


ADMIN_HELP = (
    "👑 <b>Команды администратора</b>\n"
    "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
    "🃏 «Создать карту» — фото, название, описание, цена, тираж (безграничный или число)\n"
    "⚗️ «Выпустить улучшения» — запустить гача-пул улучшений для карты "
    "(редкости: редкая/эпическая/мифическая/легендарная, можно несколько артов "
    "на одну редкость)\n"
    "⏯ «Управление улучшениями» — пауза/возобновление запущенных релизов\n"
    "🧪 «Создать крафт» — рецепт из конкретных карт-ингредиентов (в т.ч. улучшенных) "
    "-> 1 карта-результат. Бесплатно для пользователя, но с шансом провала — тогда "
    "все вложенные карты сгорают\n"
    "⏯ «Управление крафтом» — пауза/возобновление рецептов крафта\n"
    "🎛 «Кнопка крафта в меню» — показать/скрыть кнопку «🧪 Крафт» в главном меню "
    "пользователей в любой момент\n"
    "🗳 «Заявки на карты» — одобрить/отклонить карты, созданные обычными "
    f"пользователями (при одобрении с автора спишется ⭐ {CUSTOM_CARD_APPROVAL_FEE})\n"
    "💰 «Изменить баланс» — /set_balance id|@username ±сумма или abs.сумма\n"
    "💱 «Канал для выводов» — куда бот будет постить сообщения об одобренных выводах\n"
    "🎫 «Создать чек» — промокод на звёзды по ссылке\n"
    "🛡 «Модераторы» — назначить/снять модератора\n"
    "📢 «Каналы» — управлять обязательными подписками\n"
    "🚫 «Бан/Разбан» — заблокировать/разблокировать пользователя\n"
    "📊 «Статистика» — общая статистика бота"
)


@router.message(F.text == "👑 Панель администратора")
async def open_admin_panel(message: Message):
    await message.answer("👑 <b>Панель администратора</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                          parse_mode="HTML", reply_markup=admin_panel_kb())


@router.message(Command("admin_help"))
async def admin_help(message: Message):
    await message.answer(ADMIN_HELP, parse_mode="HTML")


# ============================================================
#   СОЗДАНИЕ БАЗОВОЙ КАРТЫ
# ============================================================

@router.message(F.text == "🃏 Создать карту")
async def create_card_start(message: Message, state: FSMContext):
    await state.set_state(CreateCard.photo)
    await message.answer("🃏 Пришлите фото новой карты:")


@router.message(CreateCard.photo, F.photo)
async def create_card_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(CreateCard.name)
    await message.answer("✏️ Введите название карты:")


@router.message(CreateCard.photo)
async def create_card_photo_invalid(message: Message):
    await message.answer("❗ Пришлите именно фото.")


@router.message(CreateCard.name)
async def create_card_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CreateCard.description)
    await message.answer("📝 Введите описание карты (или отправьте «-», если без описания):")


@router.message(CreateCard.description)
async def create_card_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description=None if desc == "-" else desc)
    await state.set_state(CreateCard.price)
    await message.answer("💰 Введите начальную цену карты в звёздах:")


@router.message(CreateCard.price)
async def create_card_price(message: Message, state: FSMContext):
    if not message.text.strip().replace(".", "", 1).isdigit():
        await message.answer("❗ Введите число.")
        return
    price = float(message.text.strip())
    await state.update_data(price=price)
    await state.set_state(CreateCard.stock_choice)
    await message.answer("📦 Тираж карты — сколько экземпляров сможет купить магазин?",
                          reply_markup=stock_choice_kb())


@router.callback_query(F.data == "stock:unlimited", CreateCard.stock_choice)
async def create_card_stock_unlimited(callback: CallbackQuery, state: FSMContext):
    await state.update_data(stock_total=None)
    await callback.answer()
    await _show_card_confirm(callback.message, state)


@router.callback_query(F.data == "stock:limited", CreateCard.stock_choice)
async def create_card_stock_limited(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateCard.stock_count)
    await callback.answer()
    await callback.message.answer("🔢 Введите количество экземпляров:")


@router.message(CreateCard.stock_count)
async def create_card_stock_count(message: Message, state: FSMContext):
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Введите целое число больше 0.")
        return
    await state.update_data(stock_total=int(message.text.strip()))
    await _show_card_confirm(message, state)


async def _show_card_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(CreateCard.confirm)
    stock_text = "♾ безграничный" if data.get("stock_total") is None else f"{data['stock_total']} шт."
    desc_text = f"\n{data['description']}" if data.get("description") else ""
    await message.answer_photo(
        data["photo_file_id"],
        caption=(f"🃏 <b>{data['name']}</b>{desc_text}\n\nЦена: ⭐ {data['price']:.2f}\n"
                 f"Тираж: {stock_text}\n\nВсё верно?"),
        parse_mode="HTML",
        reply_markup=confirm_kb("create_card_confirm"),
    )


@router.callback_query(F.data == "create_card_confirm", CreateCard.confirm)
async def create_card_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    card_id = await cards_db.create_card(
        data["name"], data["photo_file_id"], data["price"], callback.from_user.id,
        description=data.get("description"), stock_total=data.get("stock_total"),
    )
    await callback.answer("✅ Карта создана")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Карта «{data['name']}» создана (id {card_id}) и доступна в магазине!")


# ============================================================
#   ВЫПУСК УЛУЧШЕНИЙ (ГАЧА-РЕЛИЗ) — цикл добавления вариантов
# ============================================================

@router.message(F.text == "⚗️ Выпустить улучшения")
async def create_release_start(message: Message, state: FSMContext):
    active_cards = await cards_db.list_active_cards(limit=100)
    if not active_cards:
        await message.answer("❗ Сначала создайте хотя бы одну базовую карту.")
        return
    await state.set_state(CreateRelease.choose_base)
    await message.answer("Выберите базовую карту для выпуска улучшений:",
                          reply_markup=base_cards_pick_kb(active_cards))


@router.callback_query(F.data.startswith("pick_base:"), CreateRelease.choose_base)
async def create_release_pick_base(callback: CallbackQuery, state: FSMContext):
    card_id = int(callback.data.split(":")[1])
    release_id = await cards_db.create_release_draft(card_id, callback.from_user.id)
    await state.update_data(base_card_id=card_id, release_id=release_id, variants=[])
    await state.set_state(CreateRelease.variant_rarity)
    await callback.answer()
    await callback.message.answer("Выберите редкость нового варианта улучшения:", reply_markup=rarity_pick_kb())


@router.callback_query(F.data.startswith("rarity:"), CreateRelease.variant_rarity)
async def create_release_rarity(callback: CallbackQuery, state: FSMContext):
    rarity = callback.data.split(":")[1]
    await state.update_data(current_rarity=rarity)
    await state.set_state(CreateRelease.variant_photo)
    await callback.answer()
    await callback.message.answer(f"📸 Пришлите фото для варианта редкости «{RARITY_NAMES.get(rarity)}»:")


@router.message(CreateRelease.variant_photo, F.photo)
async def create_release_photo(message: Message, state: FSMContext):
    await state.update_data(current_photo=message.photo[-1].file_id)
    await state.set_state(CreateRelease.variant_name)
    await message.answer("✏️ Введите название этого улучшения (например «Строитель Про»):")


@router.message(CreateRelease.variant_photo)
async def create_release_photo_invalid(message: Message):
    await message.answer("❗ Пришлите именно фото.")


@router.message(CreateRelease.variant_name)
async def create_release_name(message: Message, state: FSMContext):
    data = await state.get_data()
    variant_id = await cards_db.add_variant(
        data["release_id"], data["current_rarity"], message.text.strip(), data["current_photo"]
    )
    variants = data.get("variants", [])
    variants.append({"variant_id": variant_id, "rarity": data["current_rarity"], "name": message.text.strip()})
    await state.update_data(variants=variants)
    await state.set_state(CreateRelease.confirm)

    summary = "\n".join(f"• {RARITY_NAMES.get(v['rarity'])} — «{v['name']}»" for v in variants)
    await message.answer(
        f"✅ Вариант добавлен!\n\n<b>Текущие варианты релиза:</b>\n{summary}\n\n"
        f"Добавить ещё один вариант (можно несколько на одну редкость) или опубликовать релиз?",
        parse_mode="HTML",
        reply_markup=release_draft_kb(),
    )


@router.callback_query(F.data == "add_variant", CreateRelease.confirm)
async def create_release_add_more(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateRelease.variant_rarity)
    await callback.answer()
    await callback.message.answer("Выберите редкость следующего варианта:", reply_markup=rarity_pick_kb())


@router.callback_query(F.data == "discard_release", CreateRelease.confirm)
async def create_release_discard(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cards_db.discard_draft_release(data["release_id"])
    await state.clear()
    await callback.answer("❌ Релиз отменён")
    await callback.message.answer("❌ Черновик релиза улучшений удалён.")


@router.callback_query(F.data == "publish_release", CreateRelease.confirm)
async def create_release_publish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("variants"):
        await callback.answer("Добавьте хотя бы один вариант", show_alert=True)
        return
    await cards_db.confirm_release(data["release_id"])
    await state.clear()
    await callback.answer("🚀 Опубликовано!")
    await callback.message.answer(
        "🚀 Релиз улучшений запущен! Первый час попытки улучшения стоят дороже "
        "(выше шанс на легендарную карту), затем цена снижается до базовой."
    )


# ---------------- ПАУЗА / ВОЗОБНОВЛЕНИЕ ----------------

@router.message(F.text == "⏯ Управление улучшениями")
async def manage_releases(message: Message):
    releases = await cards_db.list_all_active_releases()
    if not releases:
        await message.answer("Пока нет запущенных релизов улучшений.")
        return
    enriched = []
    for r in releases:
        card = await cards_db.get_card(r["base_card_id"])
        enriched.append({"release_id": r["release_id"], "card_name": card["name"] if card else "?",
                          "is_paused": r["is_paused"]})
    await message.answer("⏯ Релизы улучшений:", reply_markup=releases_manage_kb(enriched))


@router.callback_query(F.data.startswith("toggle_release:"))
async def cb_toggle_release(callback: CallbackQuery):
    release_id = int(callback.data.split(":")[1])
    release = await cards_db.get_release(release_id)
    if not release:
        await callback.answer("Не найдено", show_alert=True)
        return
    await cards_db.set_release_paused(release_id, not release["is_paused"])
    await callback.answer("Готово")
    releases = await cards_db.list_all_active_releases()
    enriched = []
    for r in releases:
        card = await cards_db.get_card(r["base_card_id"])
        enriched.append({"release_id": r["release_id"], "card_name": card["name"] if card else "?",
                          "is_paused": r["is_paused"]})
    await callback.message.edit_reply_markup(reply_markup=releases_manage_kb(enriched))


# ============================================================
#   ПОКАЗАТЬ / СКРЫТЬ КНОПКУ «КРАФТ» В ГЛАВНОМ МЕНЮ
# ============================================================

@router.message(F.text == "🎛 Кнопка крафта в меню")
async def craft_menu_toggle_prompt(message: Message):
    raw = await get_setting(CRAFT_MENU_SETTING_KEY, "1")
    visible = raw != "0"
    status = "✅ показана" if visible else "🚫 скрыта"
    await message.answer(
        f"🎛 <b>Кнопка «🧪 Крафт» в главном меню</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"Сейчас: {status}.\n\n"
        f"Это влияет только на видимость кнопки в меню — сам крафт как функция "
        f"продолжает работать.",
        parse_mode="HTML",
        reply_markup=craft_menu_toggle_kb(visible),
    )


@router.callback_query(F.data == "craftmenu_hide")
async def cb_craft_menu_hide(callback: CallbackQuery):
    await set_setting(CRAFT_MENU_SETTING_KEY, "0")
    await callback.answer("🙈 Кнопка «Крафт» скрыта из меню")
    await callback.message.edit_text(
        "🎛 <b>Кнопка «🧪 Крафт» в главном меню</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\nСейчас: 🚫 скрыта.",
        parse_mode="HTML",
        reply_markup=craft_menu_toggle_kb(False),
    )


@router.callback_query(F.data == "craftmenu_show")
async def cb_craft_menu_show(callback: CallbackQuery):
    await set_setting(CRAFT_MENU_SETTING_KEY, "1")
    await callback.answer("👁 Кнопка «Крафт» снова в меню")
    await callback.message.edit_text(
        "🎛 <b>Кнопка «🧪 Крафт» в главном меню</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\nСейчас: ✅ показана.",
        parse_mode="HTML",
        reply_markup=craft_menu_toggle_kb(True),
    )


# ============================================================
#   ИЗМЕНЕНИЕ БАЛАНСА
# ============================================================

@router.message(F.text == "💰 Изменить баланс")
async def set_balance_start(message: Message, state: FSMContext):
    await state.set_state(SetBalance.target)
    await message.answer("👤 Укажите ID или @username пользователя:")


@router.message(Command("set_balance"))
async def set_balance_cmd(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /set_balance id|@username ±сумма (или просто число для установки)")
        return
    await _apply_balance_change(message, parts[1], parts[2])


@router.message(SetBalance.target)
async def set_balance_target(message: Message, state: FSMContext):
    user = await users_db.resolve_user(message.text.strip())
    if not user:
        await message.answer("❗ Пользователь не найден. Попробуйте ещё раз или отправьте ID/@username.")
        return
    await state.update_data(target_id=user["user_id"], target_label=user["username"] or user["user_id"])
    await state.set_state(SetBalance.amount)
    await message.answer(
        f"Текущий баланс @{user['username'] or user['user_id']}: ⭐ {user['balance']:.2f}\n\n"
        f"Введите изменение: <code>+100</code> / <code>-50</code> — прибавить/убавить, "
        f"или просто <code>100</code> — установить баланс равным 100.",
        parse_mode="HTML",
    )


@router.message(SetBalance.amount)
async def set_balance_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await _apply_balance_change(message, str(data["target_id"]), message.text.strip())


async def _apply_balance_change(message: Message, target: str, amount_str: str):
    user = await users_db.resolve_user(target)
    if not user:
        await message.answer("❗ Пользователь не найден.")
        return
    amount_str = amount_str.strip()
    try:
        if amount_str.startswith("+") or amount_str.startswith("-"):
            delta = float(amount_str)
            await users_db.change_balance(user["user_id"], delta, "admin_adjust", "Изменение баланса админом")
            new_user = await users_db.get_user(user["user_id"])
            await message.answer(f"✅ Баланс @{user['username'] or user['user_id']} изменён на {delta:+.2f}. "
                                  f"Новый баланс: ⭐ {new_user['balance']:.2f}")
        else:
            value = float(amount_str)
            await users_db.set_balance(user["user_id"], value)
            await message.answer(f"✅ Баланс @{user['username'] or user['user_id']} установлен: ⭐ {value:.2f}")
    except ValueError:
        await message.answer("❗ Неверный формат суммы.")


# ============================================================
#   МОДЕРАТОРЫ
# ============================================================

@router.message(F.text == "🛡 Модераторы")
async def manage_moderators(message: Message):
    mods = await users_db.list_moderators()
    text = "🛡 <b>Список модераторов:</b>\n\n" + (
        "\n".join(f"• @{m['username'] or m['user_id']} (id {m['user_id']})" for m in mods) or "Пока никого нет."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=moderators_manage_kb(mods))


@router.callback_query(F.data == "add_mod")
async def cb_add_mod(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ManageModerators.add_target)
    await callback.answer()
    await callback.message.answer("👤 Укажите ID или @username нового модератора:")


@router.message(ManageModerators.add_target)
async def process_add_mod(message: Message, state: FSMContext):
    await state.clear()
    user = await users_db.resolve_user(message.text.strip())
    if not user:
        await message.answer("❗ Пользователь не найден (он должен хотя бы раз запустить бота).")
        return
    await users_db.add_moderator(user["user_id"], user["username"], message.from_user.id)
    await message.answer(f"✅ @{user['username'] or user['user_id']} назначен модератором.")


@router.callback_query(F.data.startswith("del_mod:"))
async def cb_del_mod(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    await users_db.remove_moderator(user_id)
    await callback.answer("✅ Модератор снят")
    mods = await users_db.list_moderators()
    await callback.message.edit_reply_markup(reply_markup=moderators_manage_kb(mods))


# ============================================================
#   КАНАЛЫ (обязательные подписки)
# ============================================================

@router.message(F.text == "📢 Каналы")
async def manage_channels(message: Message):
    chs = await channels_db.list_channels()
    text = "📢 <b>Обязательные каналы:</b>\n\n" + (
        "\n".join(f"• {c['title']} ({c['chat_id']})" for c in chs) or "Список пуст."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=channels_manage_kb(chs))


@router.callback_query(F.data == "add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ManageChannels.add_chat_id)
    await callback.answer()
    await callback.message.answer(
        "📢 Отправьте chat_id канала (например @mychannel или -1001234567890).\n"
        "⚠️ Бот должен быть администратором этого канала."
    )


@router.message(ManageChannels.add_chat_id)
async def process_channel_id(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.text.strip())
    await state.set_state(ManageChannels.add_title)
    await message.answer("Введите отображаемое название канала:")


@router.message(ManageChannels.add_title)
async def process_channel_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ManageChannels.add_url)
    await message.answer("Введите ссылку на канал (https://t.me/...):")


@router.message(ManageChannels.add_url)
async def process_channel_url(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await channels_db.add_channel(data["chat_id"], data["title"], message.text.strip(), message.from_user.id)
    await message.answer(f"✅ Канал «{data['title']}» добавлен в обязательные подписки.")


@router.callback_query(F.data.startswith("del_channel:"))
async def cb_del_channel(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    await channels_db.remove_channel(channel_id)
    await callback.answer("✅ Канал удалён")
    chs = await channels_db.list_channels()
    await callback.message.edit_reply_markup(reply_markup=channels_manage_kb(chs))


# ============================================================
#   БАН / РАЗБАН
# ============================================================

@router.message(F.text == "🚫 Бан/Разбан")
async def ban_menu(message: Message):
    await message.answer(
        "🚫 Используйте команды:\n"
        "<code>/ban id|@username причина</code>\n"
        "<code>/unban id|@username</code>",
        parse_mode="HTML",
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /ban id|@username [причина]")
        return
    user = await users_db.resolve_user(parts[1])
    if not user:
        await message.answer("❗ Пользователь не найден.")
        return
    reason = parts[2] if len(parts) > 2 else ""
    await users_db.ban_user(user["user_id"], reason)
    await message.answer(f"🚫 Пользователь @{user['username'] or user['user_id']} заблокирован.")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /unban id|@username")
        return
    user = await users_db.resolve_user(parts[1])
    if not user:
        await message.answer("❗ Пользователь не найден.")
        return
    await users_db.unban_user(user["user_id"])
    await message.answer(f"✅ Пользователь @{user['username'] or user['user_id']} разблокирован.")


# ============================================================
#   ЧЕКИ
# ============================================================

@router.message(F.text == "🎫 Создать чек")
async def create_check_start(message: Message, state: FSMContext):
    await state.set_state(CreateCheck.amount)
    await message.answer("🎫 Сколько звёзд получит каждый активировавший чек?")


@router.message(CreateCheck.amount)
async def create_check_amount(message: Message, state: FSMContext):
    if not message.text.strip().replace(".", "", 1).isdigit():
        await message.answer("❗ Введите число.")
        return
    await state.update_data(amount=float(message.text.strip()))
    await state.set_state(CreateCheck.activations)
    await message.answer("👥 На сколько пользователей рассчитан чек (макс. активаций)?")


@router.message(CreateCheck.activations)
async def create_check_activations(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❗ Введите целое число.")
        return
    await state.update_data(activations=int(message.text.strip()))
    data = await state.get_data()
    await state.set_state(CreateCheck.confirm)
    total = data["amount"] * data["activations"]
    await message.answer(
        f"🎫 Чек: ⭐ {data['amount']:.2f} × {data['activations']} чел. = <b>⭐ {total:.2f}</b> всего.\n\nПодтвердить создание?",
        parse_mode="HTML",
        reply_markup=confirm_kb("create_check_confirm"),
    )


@router.callback_query(F.data == "create_check_confirm", CreateCheck.confirm)
async def create_check_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    check_id, code = await checks_db.create_check(data["amount"], data["activations"], callback.from_user.id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=check_{code}"
    await callback.answer("✅ Чек создан")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ <b>Чек создан!</b>\n\n⭐ {data['amount']:.2f} на человека, до {data['activations']} активаций.\n\n"
        f"🔗 Ссылка для отправки:\n<code>{link}</code>",
        parse_mode="HTML",
    )


# ============================================================
#   ЗАЯВКИ НА ПОЛЬЗОВАТЕЛЬСКИЕ КАРТЫ
# ============================================================

@router.message(F.text == "🗳 Заявки на карты")
async def list_pending_cards(message: Message, bot: Bot):
    pending = await cards_db.list_pending_cards()
    if not pending:
        await message.answer("✅ Нет карт, ожидающих проверки.")
        return
    await message.answer(f"🗳 Ожидают проверки: {len(pending)}")
    for c in pending:
        creator = await users_db.get_user(c["created_by"])
        creator_label = f"@{creator['username']}" if creator and creator["username"] else str(c["created_by"])
        stock_text = "♾ безграничный" if c["stock_total"] is None else f"{c['stock_total']} шт."
        desc_text = f"\n{c['description']}" if c["description"] else ""
        caption = (
            f"🃏 <b>{c['name']}</b>{desc_text}\n\n"
            f"Автор: {creator_label} (id {c['created_by']})\n"
            f"Тираж: {stock_text}\n"
            f"Стартовая цена: ⭐ {c['base_price']:.2f}\n\n"
            f"При одобрении с автора спишется ⭐ {CUSTOM_CARD_APPROVAL_FEE}."
        )
        await message.answer_photo(c["photo_file_id"], caption=caption, parse_mode="HTML",
                                    reply_markup=card_review_kb(c["card_id"]))


@router.callback_query(F.data.startswith("card_approve:"))
async def cb_card_approve(callback: CallbackQuery, bot: Bot):
    card_id = int(callback.data.split(":")[1])
    card = await cards_db.get_card(card_id)
    if not card or card["approval_status"] != "pending":
        await callback.answer("Эта заявка уже обработана", show_alert=True)
        return
    creator = await users_db.get_user(card["created_by"])
    if not creator or creator["balance"] < CUSTOM_CARD_APPROVAL_FEE:
        await callback.answer(
            f"❌ У автора недостаточно звёзд (нужно ⭐ {CUSTOM_CARD_APPROVAL_FEE}). "
            f"Пусть пополнит баланс, потом одобрите снова.",
            show_alert=True,
        )
        return

    await users_db.change_balance(card["created_by"], -CUSTOM_CARD_APPROVAL_FEE, "custom_card_fee",
                                   f"Комиссия за создание карты «{card['name']}»")
    await users_db.change_balance(ADMIN_IDS[0], CUSTOM_CARD_APPROVAL_FEE, "custom_card_revenue",
                                   f"Комиссия за одобренную карту «{card['name']}»")
    await cards_db.approve_card(card_id)

    await callback.answer("✅ Одобрено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Карта «{card['name']}» одобрена и опубликована в магазине.")
    try:
        await bot.send_message(
            card["created_by"],
            f"🎉 Ваша карта «{card['name']}» одобрена и теперь доступна в магазине!\n"
            f"За создание списано ⭐ {CUSTOM_CARD_APPROVAL_FEE}.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("card_reject:"))
async def cb_card_reject(callback: CallbackQuery, bot: Bot):
    card_id = int(callback.data.split(":")[1])
    card = await cards_db.get_card(card_id)
    if not card or card["approval_status"] != "pending":
        await callback.answer("Эта заявка уже обработана", show_alert=True)
        return
    await cards_db.reject_card(card_id)
    await callback.answer("❌ Отклонено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"❌ Карта «{card['name']}» отклонена.")
    try:
        await bot.send_message(card["created_by"], f"😔 Ваша карта «{card['name']}» отклонена модерацией.")
    except Exception:
        pass


# ============================================================
#   КАНАЛ ДЛЯ ЛОГОВ ВЫВОДОВ
# ============================================================

@router.message(F.text == "💱 Канал для выводов")
async def set_withdraw_channel_prompt(message: Message, state: FSMContext):
    current = await get_setting(WITHDRAW_LOG_CHANNEL_SETTING_KEY)
    text = f"Текущий канал: <code>{current}</code>\n\n" if current else ""
    await state.set_state(SetWithdrawChannel.channel_id)
    await message.answer(
        f"{text}📤 Пришлите ID канала (например -1001234567890 или @username), куда бот будет "
        f"публиковать сообщения об одобренных заявках на вывод.\n"
        f"⚠️ Бот должен быть администратором этого канала.\n\n"
        f"Отправьте «-», чтобы отключить автопостинг.",
        parse_mode="HTML",
    )


@router.message(SetWithdrawChannel.channel_id)
async def process_withdraw_channel(message: Message, state: FSMContext):
    await state.clear()
    value = message.text.strip()
    if value == "-":
        await set_setting(WITHDRAW_LOG_CHANNEL_SETTING_KEY, "")
        await message.answer("✅ Автопостинг об одобренных выводах отключён.")
        return
    await set_setting(WITHDRAW_LOG_CHANNEL_SETTING_KEY, value)
    await message.answer(f"✅ Канал для логов выводов установлен: {value}")


# ============================================================
#   СТАТИСТИКА
# ============================================================

@router.message(F.text == "📊 Статистика")
@router.message(Command("stats"))
async def show_stats(message: Message):
    users_count = await users_db.count_users()
    mods_count = await users_db.count_moderators()
    pending_wd = await wd_db.count_pending_withdrawals()
    open_tk = await tickets_db.count_open_tickets()
    cards_count = len(await cards_db.list_active_cards(limit=100000))

    text = (
        "📊 <b>Статистика Star Card</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        f"👥 Пользователей: <b>{users_count}</b>\n"
        f"🛡 Модераторов: <b>{mods_count}</b>\n"
        f"🃏 Активных карт: <b>{cards_count}</b>\n"
        f"💸 Необработанных заявок на вывод: <b>{pending_wd}</b>\n"
        f"🎫 Открытых обращений: <b>{open_tk}</b>"
    )
    await message.answer(text, parse_mode="HTML")
