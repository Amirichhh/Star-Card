import random

from database.db import get_db
from config import CRAFT_VALUE_BONUS


async def create_recipe_draft(name: str, photo_file_id: str, success_chance: float, created_by: int) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO craft_recipes (name, photo_file_id, success_chance, created_by) VALUES (?, ?, ?, ?)",
        (name, photo_file_id, success_chance, created_by),
    )
    await db.commit()
    return cur.lastrowid


async def add_ingredient(recipe_id: int, card_type: str, card_ref_id: int, quantity: int) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO craft_ingredients (recipe_id, card_type, card_ref_id, quantity) VALUES (?, ?, ?, ?)",
        (recipe_id, card_type, card_ref_id, quantity),
    )
    await db.commit()
    return cur.lastrowid


async def list_ingredients(recipe_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM craft_ingredients WHERE recipe_id = ?", (recipe_id,))
    return await cur.fetchall()


async def publish_recipe(recipe_id: int):
    db = await get_db()
    await db.execute("UPDATE craft_recipes SET is_draft = 0 WHERE recipe_id = ?", (recipe_id,))
    await db.commit()


async def discard_recipe(recipe_id: int):
    db = await get_db()
    await db.execute("DELETE FROM craft_ingredients WHERE recipe_id = ?", (recipe_id,))
    await db.execute("DELETE FROM craft_recipes WHERE recipe_id = ?", (recipe_id,))
    await db.commit()


async def get_recipe(recipe_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM craft_recipes WHERE recipe_id = ?", (recipe_id,))
    return await cur.fetchone()


async def list_available_recipes():
    """Опубликованные и не на паузе - видны пользователям для крафта."""
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM craft_recipes WHERE is_draft = 0 AND is_paused = 0 ORDER BY recipe_id DESC"
    )
    return await cur.fetchall()


async def list_all_published_recipes():
    """Все опубликованные (вкл. на паузе) - для панели управления у админа."""
    db = await get_db()
    cur = await db.execute("SELECT * FROM craft_recipes WHERE is_draft = 0 ORDER BY recipe_id DESC")
    return await cur.fetchall()


async def set_recipe_paused(recipe_id: int, paused: bool):
    db = await get_db()
    await db.execute("UPDATE craft_recipes SET is_paused = ? WHERE recipe_id = ?",
                      (1 if paused else 0, recipe_id))
    await db.commit()


def roll_success(success_chance: float) -> bool:
    return random.random() < success_chance


async def recipe_value(recipe_id: int) -> float:
    """Ценность карты-результата = сумма текущей стоимости всех вложенных
    ингредиентов (с учётом их количества) * бонус за риск."""
    from services.valuation import resolve_card_info
    ingredients = await list_ingredients(recipe_id)
    total = 0.0
    for ing in ingredients:
        info = await resolve_card_info(ing["card_type"], ing["card_ref_id"])
        if info:
            total += info["unit_value"] * ing["quantity"]
    return round(total * CRAFT_VALUE_BONUS, 2)
