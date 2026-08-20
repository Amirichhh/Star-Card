from database.db import get_db


async def create_ticket(user_id: int, username: str | None, subject: str) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO tickets (user_id, username, subject) VALUES (?, ?, ?)",
        (user_id, username, subject),
    )
    await db.commit()
    return cur.lastrowid


async def get_ticket(ticket_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
    return await cur.fetchone()


async def get_open_ticket_for_user(user_id: int):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM tickets WHERE user_id = ? AND status = 'open' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    return await cur.fetchone()


async def list_open_tickets():
    db = await get_db()
    cur = await db.execute("SELECT * FROM tickets WHERE status = 'open' ORDER BY created_at ASC")
    return await cur.fetchall()


async def count_open_tickets() -> int:
    db = await get_db()
    cur = await db.execute("SELECT COUNT(*) as c FROM tickets WHERE status = 'open'")
    row = await cur.fetchone()
    return row["c"]


async def claim_ticket(ticket_id: int, staff_id: int):
    db = await get_db()
    await db.execute("UPDATE tickets SET claimed_by = ? WHERE ticket_id = ?", (staff_id, ticket_id))
    await db.commit()


async def close_ticket(ticket_id: int, closed_by: int):
    db = await get_db()
    await db.execute(
        "UPDATE tickets SET status = 'closed', closed_by = ?, closed_at = CURRENT_TIMESTAMP WHERE ticket_id = ?",
        (closed_by, ticket_id),
    )
    await db.commit()


async def add_message(ticket_id: int, sender_id: int, sender_role: str, text: str) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO ticket_messages (ticket_id, sender_id, sender_role, text) VALUES (?, ?, ?, ?)",
        (ticket_id, sender_id, sender_role, text),
    )
    await db.commit()
    return cur.lastrowid


async def list_messages(ticket_id: int):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC",
        (ticket_id,),
    )
    return await cur.fetchall()
