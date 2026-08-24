from aiogram.fsm.state import State, StatesGroup


class CreateCard(StatesGroup):
    photo = State()
    name = State()
    description = State()
    price = State()
    stock_choice = State()
    stock_count = State()
    confirm = State()


class CreateUserCard(StatesGroup):
    """Обычный пользователь создаёт свою карту - уходит на модерацию."""
    photo = State()
    name = State()
    description = State()
    stock_choice = State()
    stock_count = State()
    confirm = State()


class TransferStars(StatesGroup):
    target = State()
    amount = State()
    confirm = State()


class LockCard(StatesGroup):
    """Личный холдинг: пользователь сам блокирует продажу СВОИХ карт на N дней."""
    days = State()


class SetWithdrawChannel(StatesGroup):
    channel_id = State()


class CreateRelease(StatesGroup):
    """Админ выпускает пул улучшений для базовой карты.
    Цикл variant_rarity -> variant_photo -> variant_name -> (снова variant_rarity ИЛИ confirm)
    повторяется, пока админ не нажмёт «Готово, опубликовать»."""
    choose_base = State()
    variant_rarity = State()
    variant_photo = State()
    variant_name = State()
    confirm = State()


class TopUp(StatesGroup):
    custom_amount = State()


class Withdraw(StatesGroup):
    amount = State()
    requisites = State()
    confirm = State()


class AutoSell(StatesGroup):
    """Мгновенная продажа N обычных карт боту по текущему курсу (курс после этого падает)."""
    quantity = State()
    confirm = State()


class UpgradeCards(StatesGroup):
    """Улучшение (гача) N обычных карт одного вида за раз."""
    quantity = State()
    confirm = State()


class TransferCard(StatesGroup):
    """Передача улучшенных карт другому пользователю."""
    quantity = State()
    target = State()
    confirm = State()


class CreateCraft(StatesGroup):
    """Админ создаёт рецепт крафта: конкретные карты-ингредиенты (любого типа,
    включая улучшенные) -> 1 карта-результат. Бесплатно, но с шансом провала,
    при котором все ингредиенты сгорают.
    Цикл: ingredient_type -> ingredient_pick -> ingredient_qty -> (снова
    ingredient_type ИЛИ confirm), пока админ не нажмёт «Готово, опубликовать»."""
    name = State()
    photo = State()
    success_chance = State()
    ingredient_type = State()
    ingredient_pick = State()
    ingredient_qty = State()
    confirm = State()


class SetBalance(StatesGroup):
    target = State()
    amount = State()


class ManageModerators(StatesGroup):
    add_target = State()
    remove_confirm = State()


class ManageChannels(StatesGroup):
    add_chat_id = State()
    add_title = State()
    add_url = State()


class BanUser(StatesGroup):
    target = State()
    reason = State()


class UnbanUser(StatesGroup):
    target = State()


class CreateCheck(StatesGroup):
    amount = State()
    activations = State()
    confirm = State()


class SupportTicket(StatesGroup):
    subject = State()
    chatting = State()


class StaffReply(StatesGroup):
    replying = State()


class ShopSearch(StatesGroup):
    query = State()
