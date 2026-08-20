from database.db import get_db


async def create_withdraw_request(user_id: int, username: str | None, amount: float, requisites: str) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO withdraw_requests (user_id, username, amount, requisites) VALUES (?, ?, ?, ?)",
        (user_id, username, amount, requisites),
    )
    await db.commit()
    return cur.lastrowid


async def get_withdraw_request(request_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM withdraw_requests WHERE request_id = ?", (request_id,))
    return await cur.fetchone()


async def list_pending_withdrawals():
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM withdraw_requests WHERE status = 'pending' ORDER BY created_at ASC"
    )
    return await cur.fetchall()


async def count_pending_withdrawals() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) as c FROM withdraw_requests WHERE status = 'pending'")
    row = await cur.fetchone()
    return row["c"]


async def close_withdraw_request(request_id: int, status: str, closed_by: int):
    db = await get_db()
    await db.execute(
        "UPDATE withdraw_requests SET status = ?, closed_by = ?, closed_at = CURRENT_TIMESTAMP WHERE request_id = ?",
        (status, closed_by, request_id),
    )
    await db.commit()


async def list_user_withdrawals(user_id: int):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM withdraw_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (user_id,),
    )
    return await cur.fetchall()
