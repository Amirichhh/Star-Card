from database.db import get_db


async def add_channel(chat_id: str, title: str, url: str, added_by: int) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO channels (chat_id, title, url, added_by) VALUES (?, ?, ?, ?)",
        (chat_id, title, url, added_by),
    )
    await db.commit()
    return cur.lastrowid


async def remove_channel(channel_id: int):
    db = await get_db()
    await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    await db.commit()


async def list_channels():
    db = await get_db()
    cur = await db.execute("SELECT * FROM channels ORDER BY channel_id ASC")
    return await cur.fetchall()


async def get_channel(channel_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,))
    return await cur.fetchone()
