"""SQLite storage. One file, zero ops. All tables are created on startup."""
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_inbox (
  provider TEXT, message_id TEXT, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
  phone TEXT NOT NULL, received_at REAL NOT NULL,
  PRIMARY KEY(provider, message_id));
CREATE INDEX IF NOT EXISTS webhook_window ON webhook_inbox(provider,phone,received_at);

CREATE TABLE IF NOT EXISTS shared_links (
  token TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL, expires_at REAL NOT NULL);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, aliases TEXT DEFAULT '[]', phone TEXT UNIQUE,
  lang TEXT DEFAULT 'hi-IN', role TEXT DEFAULT 'customer', credit_limit REAL DEFAULT 0,
  opted_in INTEGER DEFAULT 0, note TEXT DEFAULT '', created_at REAL);

CREATE TABLE IF NOT EXISTS catalog (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, aliases TEXT DEFAULT '[]', unit TEXT DEFAULT '', price REAL DEFAULT 0);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, direction TEXT, phone TEXT, kind TEXT, text TEXT, buttons TEXT,
  media TEXT, meta TEXT, created_at REAL);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, phone TEXT, contact_id INTEGER, kind TEXT, audio_sha TEXT,
  transcript TEXT, transcript_b TEXT, lang TEXT, plan TEXT, created_at REAL);

CREATE TABLE IF NOT EXISTS pending (
  id INTEGER PRIMARY KEY, event_id INTEGER, phone TEXT, actions TEXT, reasons TEXT,
  status TEXT DEFAULT 'open', created_at REAL);

CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY, contact_id INTEGER, amount REAL, kind TEXT, note TEXT, due_date TEXT,
  status TEXT DEFAULT 'confirmed', event_id INTEGER, audio_sha TEXT, actor TEXT,
  ref_id INTEGER, prev_hash TEXT, hash TEXT, created_at REAL);

CREATE TABLE IF NOT EXISTS ledger_status (
  id INTEGER PRIMARY KEY, ledger_id INTEGER NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ledger_status_by_entry ON ledger_status(ledger_id, id);
CREATE VIEW IF NOT EXISTS ledger_current AS
  SELECT l.id, l.contact_id, l.amount, l.kind, l.note, l.due_date,
    COALESCE((SELECT s.status FROM ledger_status s WHERE s.ledger_id=l.id ORDER BY s.id DESC LIMIT 1),
             l.status) AS status,
    l.event_id, l.audio_sha, l.actor, l.ref_id, l.prev_hash, l.hash, l.created_at
  FROM ledger l;

CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY, ledger_id INTEGER, contact_id INTEGER, kind TEXT, amount REAL,
  date TEXT, text TEXT, audio_sha TEXT, status TEXT DEFAULT 'open', created_at REAL);

CREATE TABLE IF NOT EXISTS polls (
  id INTEGER PRIMARY KEY, kind TEXT DEFAULT 'poll', question TEXT, options TEXT, deadline REAL,
  created_by TEXT, status TEXT DEFAULT 'open', created_at REAL);

CREATE TABLE IF NOT EXISTS poll_targets (
  poll_id INTEGER, contact_id INTEGER, answer TEXT, answered_at REAL, nudges INTEGER DEFAULT 0,
  called INTEGER DEFAULT 0, PRIMARY KEY (poll_id, contact_id));

CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE, kind TEXT, html TEXT, source TEXT, created_at REAL);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY, template TEXT, contact_id INTEGER, path TEXT, fields TEXT,
  status TEXT, created_at REAL);

CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY, actor TEXT, summary TEXT, action TEXT, status TEXT DEFAULT 'open', created_at REAL);

CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY, contact_id INTEGER, text TEXT, due_at REAL, status TEXT DEFAULT 'open', created_at REAL);

CREATE TABLE IF NOT EXISTS attendance (
  id INTEGER PRIMARY KEY, contact_id INTEGER, date TEXT, status TEXT, by TEXT, created_at REAL,
  UNIQUE(contact_id, date));

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, actor TEXT, action TEXT, detail TEXT, created_at REAL);
"""

DEFAULT_SETTINGS = {
    "shop_name": "",
    "business_type": "",
    "business_desc": "",
    "onboarded": "0",
    "features": "",
    "bot_mode": "auto",  # auto | paused (watch only: messages are recorded, the bot doesn't reply)
    "owner_phone": "",
    "owner_lang": "kn-IN",
    "confirm_money": "always",  # always | risky
    "big_amount": "2000",  # staff entries above this need owner approval
    "readback_amount": "500",  # amounts at/above this are read back in words
    "voice_replies": "1",
    "customer_loop": "1",
    "upi_id": "",
    "summary_time": "21:00",
    "nudge_after_min": "30",
    "call_after_min": "60",
    "fanout_approval": "3",  # messages to more than N people need owner approval
}


def now() -> float:
    return time.time()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_conn = connect()
_lock = threading.RLock()


@contextmanager
def tx():
    """Short, synchronous write transaction. Nested helpers join the caller's transaction."""
    with _lock:
        if _conn.in_transaction:
            yield _conn
            return
        # Reserve the writer before reading the chain head, including across processes.
        _conn.execute("BEGIN IMMEDIATE")
        try:
            yield _conn
            _conn.commit()
        except Exception:
            _conn.rollback()
            raise


def init() -> None:
    with tx():
        _init_schema()


def _init_schema() -> None:
    # executescript would commit a shop reset halfway through.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            _conn.execute(statement)
    cols = {r["name"] for r in q("PRAGMA table_info(contacts)")}
    if "paused" not in cols:  # per-chat human takeover
        _conn.execute("ALTER TABLE contacts ADD COLUMN paused INTEGER DEFAULT 0")
    if "reply_mode" not in cols:  # Voice Passport: how this person wants replies (both | voice | text)
        _conn.execute("ALTER TABLE contacts ADD COLUMN reply_mode TEXT DEFAULT 'both'")
    for k, v in DEFAULT_SETTINGS.items():
        _conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()) -> dict | None:
    with _lock:
        r = _conn.execute(sql, args).fetchone()
        return dict(r) if r else None


def run(sql: str, args: tuple = ()) -> int:
    with tx() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def reset() -> str:
    """Archive the shop's related tables together, then create a fresh empty shop."""
    archive = datetime.now(timezone.utc).strftime("archive_%Y%m%dT%H%M%S%fZ")
    with tx() as conn:
        conn.execute("DROP VIEW IF EXISTS ledger_current")
        # Keep provider receipt IDs so an old redelivery cannot enter the new shop.
        conn.execute("UPDATE webhook_inbox SET state='retired', payload='{}' WHERE state!='retired'")
        tables = q("SELECT name FROM sqlite_master WHERE type='table' "
                   "AND name NOT GLOB 'sqlite_*' AND name NOT GLOB 'archive_*' AND name!='webhook_inbox'")
        for table in tables:
            name = table["name"]
            # Explicit index names are database-wide. Free their names for the new shop.
            indexes = q("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                        (name,))
            for index in indexes:
                conn.execute('DROP INDEX "' + index["name"].replace('"', '""') + '"')
            quoted = name.replace('"', '""')
            conn.execute(f'ALTER TABLE "{quoted}" RENAME TO "{archive}_{quoted}"')
        _init_schema()
    return archive


def setting(key: str) -> str:
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str) -> None:
    run("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)))


def audit(actor: str, action: str, detail) -> None:
    run("INSERT INTO audit(actor, action, detail, created_at) VALUES (?,?,?,?)",
        (actor, action, json.dumps(detail, ensure_ascii=False) if not isinstance(detail, str) else detail, now()))
