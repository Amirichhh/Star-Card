"""
Единая функция оценки "текущей стоимости" карты любого типа (base/upgrade).
Используется там, где нужно посчитать ценность произвольной карты по её
(card_type, card_ref_id) - например, при расчёте стоимости ингредиентов крафта.
"""

from database import cards as cards_db
from config import RARITY_NAMES


async def resolve_card_info(card_type: str, ref_id: int):
    """Возвращает dict {name, photo_file_id, unit_value, label, rarity} либо None,
    если карта была удалена/не найдена."""
    if card_type == "base":
        card = await cards_db.get_card(ref_id)
        if not card:
            return None
        return {
            "name": card["name"], "photo_file_id": card["photo_file_id"],
            "unit_value": card["current_rate"], "label": card["name"], "rarity": None,
        }

    if card_type == "upgrade":
        variant = await cards_db.get_variant(ref_id)
        if not variant:
            return None
        release = await cards_db.get_release(variant["release_id"])
        card = await cards_db.get_card(release["base_card_id"]) if release else None
        if not card:
            return None
        value = cards_db.variant_value(card["current_rate"], variant["rarity"])
        label = f"{RARITY_NAMES.get(variant['rarity'], variant['rarity'])} «{variant['name']}»"
        return {
            "name": variant["name"], "photo_file_id": variant["photo_file_id"],
            "unit_value": value, "label": label, "rarity": variant["rarity"],
        }

    return None
