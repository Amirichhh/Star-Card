import datetime as dt

from database.db import get_db


async def lock(user_id: int, card_type: str, ref_id: int, days: float):
    until = dt.datetime.utcnow() + dt.timedelta(days=days)
    db = await get_db()
    await db.execute(
        "INSERT INTO holdings (user_id, card_type, card_ref_id, locked_until) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, card_type, card_ref_id) DO UPDATE SET locked_until = excluded.locked_until",
        (user_id, card_type, ref_id, until.strftime("%Y-%m-%d %H:%M:%S")),
    )
    await db.commit()


async def unlock(user_id: int, card_type: str, ref_id: int):
    db = await get_db()
    await db.execute(
        "DELETE FROM holdings WHERE user_id = ? AND card_type = ? AND card_ref_id = ?",
        (user_id, card_type, ref_id),
    )
    await db.commit()


async def get_lock(user_id: int, card_type: str, ref_id: int):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM holdings WHERE user_id = ? AND card_type = ? AND card_ref_id = ?",
        (user_id, card_type, ref_id),
    )
    return await cur.fetchone()


async def is_locked(user_id: int, card_type: str, ref_id: int) -> tuple[bool, str | None]:
    """Возвращает (заблокировано_ли, дата_до_которой) для конкретного пользователя."""
    row = await get_lock(user_id, card_type, ref_id)
    if not row:
        return False, None
    try:
        until = dt.datetime.strptime(row["locked_until"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return False, None
    if dt.datetime.utcnow() < until:
        return True, row["locked_until"]
    return False, None
