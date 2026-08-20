import secrets
from database.db import get_db


def generate_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12]


async def create_check(amount_per_user: float, max_activations: int, created_by: int) -> tuple[int, str]:
    code = generate_code()
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO checks (code, amount_per_user, max_activations, created_by) VALUES (?, ?, ?, ?)",
        (code, amount_per_user, max_activations, created_by),
    )
    await db.commit()
    return cur.lastrowid, code


async def get_check_by_code(code: str):
    db = await get_db()
    cur = await db.execute("SELECT * FROM checks WHERE code = ?", (code,))
    return await cur.fetchone()


async def has_activated(check_id: int, user_id: int) -> bool:
    db = await get_db()
    cur = await db.execute(
        "SELECT 1 FROM check_activations WHERE check_id = ? AND user_id = ?", (check_id, user_id)
    )
    return await cur.fetchone() is not None


async def activate_check(check_id: int, user_id: int):
    db = await get_db()
    await db.execute(
        "INSERT INTO check_activations (check_id, user_id) VALUES (?, ?)", (check_id, user_id)
    )
    await db.execute(
        "UPDATE checks SET used_activations = used_activations + 1 WHERE check_id = ?", (check_id,)
    )
    await db.commit()


async def list_active_checks_by_admin(created_by: int):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM checks WHERE created_by = ? AND is_active = 1 ORDER BY created_at DESC",
        (created_by,),
    )
    return await cur.fetchall()


async def deactivate_check(check_id: int):
    db = await get_db()
    await db.execute("UPDATE checks SET is_active = 0 WHERE check_id = ?", (check_id,))
    await db.commit()
