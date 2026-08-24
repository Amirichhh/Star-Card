import os
import aiosqlite

from config import DB_PATH

_connection: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _connection
    if _connection is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _connection = await aiosqlite.connect(DB_PATH)
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA foreign_keys = ON")
    return _connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    balance REAL DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    ban_reason TEXT,
    joined_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS moderators (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    appointed_by INTEGER,
    appointed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cards (
    card_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    photo_file_id TEXT NOT NULL,
    base_price REAL NOT NULL,
    current_rate REAL NOT NULL,
    day_open_rate REAL NOT NULL,
    day_high_rate REAL NOT NULL,
    day_date TEXT NOT NULL,
    stock_total INTEGER,              -- NULL = безграничный тираж
    stock_left INTEGER,               -- NULL = безграничный тираж
    is_user_created INTEGER DEFAULT 0,
    approval_status TEXT DEFAULT 'approved',  -- pending | approved | rejected (для карт от юзеров)
    locked_until TEXT,                -- до какой даты создатель заблокировал куплю/продажу карты
    is_active INTEGER DEFAULT 1,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- "Улучшение" карты - это релиз гача-пула для конкретной базовой карты.
-- Внутри одного релиза админ может создать сразу несколько вариантов (артов)
-- на каждую редкость. Пока релиз в статусе черновика (is_draft=1), он не виден
-- пользователям. После подтверждения (is_draft=0, started_at=now) запускается
-- отсчёт цены (50 -> 15 звёзд за час). Паузу можно ставить/снимать в любой момент.
CREATE TABLE IF NOT EXISTS upgrade_releases (
    release_id INTEGER PRIMARY KEY AUTOINCREMENT,
    base_card_id INTEGER NOT NULL REFERENCES cards(card_id),
    is_draft INTEGER DEFAULT 1,
    is_paused INTEGER DEFAULT 0,
    started_at TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS upgrade_variants (
    variant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id INTEGER NOT NULL REFERENCES upgrade_releases(release_id),
    rarity TEXT NOT NULL,
    name TEXT NOT NULL,
    photo_file_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- "Крафт" - ингредиенты задаются поштучно и могут быть ЛЮБОГО типа
-- (обычная карта / конкретная улучшенная карта).
-- Крафт бесплатный (звёзды не берутся), но ингредиенты списываются ВСЕГДА,
-- независимо от результата - а сам результат выпадает только с шансом
-- success_chance. Не повезло - все вложенные карты просто сгорают.
CREATE TABLE IF NOT EXISTS craft_recipes (
    recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    photo_file_id TEXT NOT NULL,
    success_chance REAL NOT NULL,     -- 0.0 - 1.0
    is_draft INTEGER DEFAULT 1,
    is_paused INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS craft_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES craft_recipes(recipe_id),
    card_type TEXT NOT NULL,          -- 'base' | 'upgrade'
    card_ref_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    card_type TEXT NOT NULL,          -- 'base' | 'upgrade' | 'craft'
    card_ref_id INTEGER NOT NULL,     -- cards.card_id / upgrade_variants.variant_id / craft_recipes.recipe_id
    bought_price REAL NOT NULL,
    acquired_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount REAL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS withdraw_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    amount REAL,
    requisites TEXT,
    status TEXT DEFAULT 'pending',    -- pending | approved | declined
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    closed_by INTEGER,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    subject TEXT,
    status TEXT DEFAULT 'open',       -- open | closed
    claimed_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    closed_by INTEGER,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(ticket_id),
    sender_id INTEGER,
    sender_role TEXT,                 -- user | staff
    text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    added_by INTEGER,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    amount_per_user REAL,
    max_activations INTEGER,
    used_activations INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS check_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id INTEGER NOT NULL REFERENCES checks(check_id),
    user_id INTEGER,
    activated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(check_id, user_id)
);

-- Личный "холдинг" карты: пользователь сам блокирует СВОИ конкретные карты
-- (любого типа) на выбранный срок и не может их продать/подарить, пока не
-- снимет блокировку или не истечёт срок. Никак не влияет на других пользователей.
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    card_type TEXT NOT NULL,
    card_ref_id INTEGER NOT NULL,
    locked_until TEXT NOT NULL,
    UNIQUE(user_id, card_type, card_ref_id)
);

-- Простое хранилище настроек ключ-значение (например id канала для логов выводов).
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()
    await _migrate(db)


async def _migrate(db):
    """Лёгкие миграции для баз, созданных до появления новых колонок.
    Старые карты при этом остаются безграничными (stock_total/stock_left = NULL)
    и одобренными (approval_status = 'approved')."""
    cur = await db.execute("PRAGMA table_info(cards)")
    columns = {row["name"] for row in await cur.fetchall()}
    migrations = {
        "stock_total": "ALTER TABLE cards ADD COLUMN stock_total INTEGER",
        "stock_left": "ALTER TABLE cards ADD COLUMN stock_left INTEGER",
        "description": "ALTER TABLE cards ADD COLUMN description TEXT",
        "is_user_created": "ALTER TABLE cards ADD COLUMN is_user_created INTEGER DEFAULT 0",
        "approval_status": "ALTER TABLE cards ADD COLUMN approval_status TEXT DEFAULT 'approved'",
        "locked_until": "ALTER TABLE cards ADD COLUMN locked_until TEXT",
    }
    for col, ddl in migrations.items():
        if col not in columns:
            await db.execute(ddl)
    await db.commit()


async def get_setting(key: str, default: str | None = None) -> str | None:
    db = await get_db()
    cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else default


async def set_setting(key: str, value: str):
    db = await get_db()
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    await db.commit()
