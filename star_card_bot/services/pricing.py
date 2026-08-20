"""
Алгоритм курса карты, похожий на биржевой (по типу спотовых крипто-бирж):

- У каждой карты (базовой и улучшенной) есть текущий курс current_rate.
- При каждой сделке (покупка в магазине у админа ИЛИ сделка на бирже между
  пользователями) курс сдвигается в сторону цены сделки (экспоненциальное
  скользящее среднее - EMA), плюс небольшое давление спроса/предложения:
  покупки толкают курс вверх, продажи - вниз.
- Курс не может упасть ниже RATE_MIN_FACTOR от базовой (первоначальной) цены.

Это простая, но живая модель: чем активнее покупают карту - тем быстрее
растёт её курс, чем активнее продают - тем быстрее падает.
"""

from config import RATE_ALPHA, RATE_BUY_PRESSURE, RATE_SELL_PRESSURE, RATE_MIN_FACTOR


def apply_trade(current_rate: float, trade_price: float, side: str, base_price: float) -> float:
    """
    side: 'buy' - кто-то купил карту (спрос), 'sell' - кто-то продал (предложение)
    """
    pressure = RATE_BUY_PRESSURE if side == "buy" else -RATE_SELL_PRESSURE
    new_rate = current_rate + (trade_price - current_rate) * RATE_ALPHA
    new_rate = new_rate * (1 + pressure)

    min_rate = base_price * RATE_MIN_FACTOR
    if new_rate < min_rate:
        new_rate = min_rate
    return round(new_rate, 2)


def rate_change_percent(old_rate: float, new_rate: float) -> float:
    if old_rate == 0:
        return 0.0
    return round((new_rate - old_rate) / old_rate * 100, 2)
