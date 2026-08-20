from database.db import get_db
from config import ADMIN_IDS


async def ensure_user(user_id: int, username: str | None, full_name: str | None):
    db = await get_db()
    cur = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    if row is None:
        await db.execute(
            "INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )
        await db.commit()
    else:
        await db.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
            (username, full_name, user_id),
        )
        await db.commit()


async def get_user(user_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await cur.fetchone()


async def get_user_by_username(username: str):
    username = username.lstrip("@")
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,))
    return await cur.fetchone()


async def resolve_user(identifier: str):
    """Найти пользователя по ID или @username."""
    identifier = identifier.strip()
    if identifier.startswith("@"):
        return await get_user_by_username(identifier)
    if identifier.lstrip("-").isdigit():
        return await get_user(int(identifier))
    return await get_user_by_username(identifier)


async def change_balance(user_id: int, delta: float, tx_type: str, description: str = ""):
    db = await get_db()
    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, tx_type, delta, description),
    )
    await db.commit()


async def set_balance(user_id: int, amount: float):
    db = await get_db()
    await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, 'admin_set', ?, 'Баланс установлен админом')",
        (user_id, amount),
    )
    await db.commit()


async def ban_user(user_id: int, reason: str = ""):
    db = await get_db()
    await db.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))
    await db.commit()


async def unban_user(user_id: int):
    db = await get_db()
    await db.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))
    await db.commit()


async def count_users() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) as c FROM users")
    row = await cur.fetchone()
    return row["c"]


# ---------------- MODERATORS ----------------

async def add_moderator(user_id: int, username: str | None, appointed_by: int):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO moderators (user_id, username, appointed_by) VALUES (?, ?, ?)",
        (user_id, username, appointed_by),
    )
    await db.commit()


async def remove_moderator(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM moderators WHERE user_id = ?", (user_id,))
    await db.commit()


async def is_moderator(user_id: int) -> bool:
    db = await get_db()
    cur = await db.execute("SELECT 1 FROM moderators WHERE user_id = ?", (user_id,))
    return await cur.fetchone() is not None


async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def is_staff(user_id: int) -> bool:
    return await is_admin(user_id) or await is_moderator(user_id)


async def list_moderators():
    db = await get_db()
    cur = await db.execute("SELECT * FROM moderators ORDER BY appointed_at DESC")
    return await cur.fetchall()


async def count_moderators() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) as c FROM moderators")
    row = await cur.fetchone()
    return row["c"]
