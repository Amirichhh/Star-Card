from database.db import get_db


async def add_bulk(user_id: int, card_type: str, card_ref_id: int, bought_price: float, count: int = 1):
    """Добавить count экземпляров карты пользователю (по одной строке на экземпляр -
    это удобно для FIFO-снятия при продаже/улучшении)."""
    db = await get_db()
    rows = [(user_id, card_type, card_ref_id, bought_price) for _ in range(count)]
    await db.executemany(
        "INSERT INTO user_cards (user_id, card_type, card_ref_id, bought_price) VALUES (?, ?, ?, ?)",
        rows,
    )
    await db.commit()


async def add_to_inventory(user_id: int, card_type: str, card_ref_id: int, bought_price: float) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO user_cards (user_id, card_type, card_ref_id, bought_price) VALUES (?, ?, ?, ?)",
        (user_id, card_type, card_ref_id, bought_price),
    )
    await db.commit()
    return cur.lastrowid


async def count_owned(user_id: int, card_type: str, card_ref_id: int) -> int:
    db = await get_db()
    cur = await db.execute(
        "SELECT COUNT(*) as c FROM user_cards WHERE user_id = ? AND card_type = ? AND card_ref_id = ?",
        (user_id, card_type, card_ref_id),
    )
    row = await cur.fetchone()
    return row["c"]


async def take_units(user_id: int, card_type: str, card_ref_id: int, qty: int) -> list[int]:
    """Забирает (удаляет) qty штук карты у пользователя, возвращает список bought_price
    для расчёта прибыли/убытка. Кидает ValueError, если карт не хватает."""
    db = await get_db()
    cur = await db.execute(
        "SELECT id, bought_price FROM user_cards WHERE user_id = ? AND card_type = ? AND card_ref_id = ? "
        "ORDER BY id ASC LIMIT ?",
        (user_id, card_type, card_ref_id, qty),
    )
    rows = await cur.fetchall()
    if len(rows) < qty:
        raise ValueError("Недостаточно карт")
    ids = [r["id"] for r in rows]
    prices = [r["bought_price"] for r in rows]
    await db.executemany("DELETE FROM user_cards WHERE id = ?", [(i,) for i in ids])
    await db.commit()
    return prices


async def list_grouped_inventory(user_id: int):
    """Группирует карты пользователя по типу+ref_id: сколько штук и сколько вложено."""
    db = await get_db()
    cur = await db.execute(
        "SELECT card_type, card_ref_id, COUNT(*) as qty, SUM(bought_price) as invested "
        "FROM user_cards WHERE user_id = ? GROUP BY card_type, card_ref_id ORDER BY card_type, card_ref_id",
        (user_id,),
    )
    return await cur.fetchall()


async def count_user_cards(user_id: int) -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) as c FROM user_cards WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return row["c"]
