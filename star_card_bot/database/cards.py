import random
import datetime as dt

from database.db import get_db
from config import (
    RARITY_MULTIPLIERS, RARITY_DROP_RATES,
    UPGRADE_LAUNCH_PRICE, UPGRADE_BASE_PRICE,
    UPGRADE_DECAY_MINUTES, UPGRADE_DECAY_STEP_MINUTES,
)


def _today() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


# ---------------- BASE CARDS ----------------

async def create_card(name: str, photo_file_id: str, base_price: float, created_by: int) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO cards (name, photo_file_id, base_price, current_rate, day_open_rate, day_high_rate, day_date, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, photo_file_id, base_price, base_price, base_price, base_price, _today(), created_by),
    )
    await db.commit()
    return cur.lastrowid


async def get_card(card_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,))
    row = await cur.fetchone()
    if row:
        row = await _ensure_daily_reset(row)
    return row


async def list_active_cards(search: str | None = None, limit: int = 6, offset: int = 0):
    db = await get_db()
    if search:
        cur = await db.execute(
            "SELECT * FROM cards WHERE is_active = 1 AND name LIKE ? ORDER BY card_id DESC LIMIT ? OFFSET ?",
            (f"%{search}%", limit, offset),
        )
    else:
        cur = await db.execute(
            "SELECT * FROM cards WHERE is_active = 1 ORDER BY card_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    return await cur.fetchall()


async def count_active_cards(search: str | None = None) -> int:
    db = await get_db()
    if search:
        cur = await db.execute("SELECT COUNT(*) as c FROM cards WHERE is_active = 1 AND name LIKE ?", (f"%{search}%",))
    else:
        cur = await db.execute("SELECT COUNT(*) as c FROM cards WHERE is_active = 1")
    row = await cur.fetchone()
    return row["c"]


async def set_card_active(card_id: int, active: bool):
    db = await get_db()
    await db.execute("UPDATE cards SET is_active = ? WHERE card_id = ?", (1 if active else 0, card_id))
    await db.commit()


async def _ensure_daily_reset(row):
    """Если наступил новый день (UTC) - сбрасываем дневной курс открытия/максимум."""
    today = _today()
    if row["day_date"] != today:
        db = await get_db()
        await db.execute(
            "UPDATE cards SET day_open_rate = ?, day_high_rate = ?, day_date = ? WHERE card_id = ?",
            (row["current_rate"], row["current_rate"], today, row["card_id"]),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM cards WHERE card_id = ?", (row["card_id"],))
        row = await cur.fetchone()
    return row


async def update_card_rate(card_id: int, new_rate: float):
    db = await get_db()
    card = await get_card(card_id)
    new_high = max(new_rate, card["day_high_rate"]) if card else new_rate
    await db.execute(
        "UPDATE cards SET current_rate = ?, day_high_rate = ? WHERE card_id = ?",
        (new_rate, new_high, card_id),
    )
    await db.commit()


def day_change_percent(card) -> float:
    if not card["day_open_rate"]:
        return 0.0
    return round((card["current_rate"] - card["day_open_rate"]) / card["day_open_rate"] * 100, 2)


# ---------------- UPGRADE RELEASES (гача-релизы) ----------------

async def create_release_draft(base_card_id: int, created_by: int) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO upgrade_releases (base_card_id, is_draft, created_by) VALUES (?, 1, ?)",
        (base_card_id, created_by),
    )
    await db.commit()
    return cur.lastrowid


async def add_variant(release_id: int, rarity: str, name: str, photo_file_id: str) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO upgrade_variants (release_id, rarity, name, photo_file_id) VALUES (?, ?, ?, ?)",
        (release_id, rarity, name, photo_file_id),
    )
    await db.commit()
    return cur.lastrowid


async def confirm_release(release_id: int):
    db = await get_db()
    await db.execute(
        "UPDATE upgrade_releases SET is_draft = 0, started_at = CURRENT_TIMESTAMP WHERE release_id = ?",
        (release_id,),
    )
    await db.commit()


async def discard_draft_release(release_id: int):
    db = await get_db()
    await db.execute("DELETE FROM upgrade_variants WHERE release_id = ?", (release_id,))
    await db.execute("DELETE FROM upgrade_releases WHERE release_id = ?", (release_id,))
    await db.commit()


async def get_release(release_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM upgrade_releases WHERE release_id = ?", (release_id,))
    return await cur.fetchone()


async def get_variants_of_release(release_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM upgrade_variants WHERE release_id = ?", (release_id,))
    return await cur.fetchall()


async def get_variant(variant_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM upgrade_variants WHERE variant_id = ?", (variant_id,))
    return await cur.fetchone()


async def get_active_release_for_card(base_card_id: int):
    """Последний запущенный (не черновик, не на паузе) релиз улучшений для базовой карты."""
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM upgrade_releases WHERE base_card_id = ? AND is_draft = 0 AND is_paused = 0 "
        "ORDER BY started_at DESC LIMIT 1",
        (base_card_id,),
    )
    return await cur.fetchone()


async def list_releases_for_card(base_card_id: int):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM upgrade_releases WHERE base_card_id = ? AND is_draft = 0 ORDER BY started_at DESC",
        (base_card_id,),
    )
    return await cur.fetchall()


async def list_all_active_releases():
    db = await get_db()
    cur = await db.execute("SELECT * FROM upgrade_releases WHERE is_draft = 0 ORDER BY started_at DESC")
    return await cur.fetchall()


async def set_release_paused(release_id: int, paused: bool):
    db = await get_db()
    await db.execute("UPDATE upgrade_releases SET is_paused = ? WHERE release_id = ?", (1 if paused else 0, release_id))
    await db.commit()


def current_pull_price(release_row) -> float:
    """Цена одной попытки улучшения: 50 звёзд в первый час, далее ступенями до 15 звёзд."""
    if not release_row["started_at"]:
        return UPGRADE_LAUNCH_PRICE
    started = dt.datetime.strptime(release_row["started_at"], "%Y-%m-%d %H:%M:%S")
    elapsed_min = (dt.datetime.utcnow() - started).total_seconds() / 60
    if elapsed_min >= UPGRADE_DECAY_MINUTES:
        return UPGRADE_BASE_PRICE
    steps_total = UPGRADE_DECAY_MINUTES / UPGRADE_DECAY_STEP_MINUTES
    step_now = int(elapsed_min // UPGRADE_DECAY_STEP_MINUTES)
    frac = step_now / steps_total
    price = UPGRADE_LAUNCH_PRICE - (UPGRADE_LAUNCH_PRICE - UPGRADE_BASE_PRICE) * frac
    return round(price, 2)


async def roll_variant_for_release(release_id: int):
    """Разыгрывает редкость по шансам, затем случайный конкретный арт этой редкости."""
    variants = await get_variants_of_release(release_id)
    if not variants:
        return None

    available_rarities = {v["rarity"] for v in variants}
    weights = {r: w for r, w in RARITY_DROP_RATES.items() if r in available_rarities}
    if not weights:
        return None
    total = sum(weights.values())
    rarities, probs = zip(*[(r, w / total) for r, w in weights.items()])
    rolled_rarity = random.choices(rarities, weights=probs, k=1)[0]

    candidates = [v for v in variants if v["rarity"] == rolled_rarity]
    return random.choice(candidates)


def variant_value(base_card_current_rate: float, rarity: str) -> float:
    """Текущая ценность улучшенной карты = курс базовой карты * множитель редкости."""
    mult = RARITY_MULTIPLIERS.get(rarity, 1.15)
    return round(base_card_current_rate * mult, 2)
