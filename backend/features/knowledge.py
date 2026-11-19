"""The bot's knowledge base ("brain"): files and facts the owner gives it.

* Files: forms, price lists, fee structures, invoice formats (PDF/image). Each has an audience
  (which role it is for). The owner can say "parents ko fee structure bhejo" and Bolo shares it.
* Facts: short text the bot uses to answer questions ("timings 9-9, Sunday closed").
Uploaded files are read by Sarvam Document AI when a key is present, so their text is searchable.
"""
import datetime as dt
import os
import re
import shutil

from rapidfuzz import fuzz

import config
import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge (
  id INTEGER PRIMARY KEY, title TEXT, kind TEXT, audience TEXT DEFAULT 'customer', path TEXT, mime TEXT,
  text TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS rule_drafts (
  id INTEGER PRIMARY KEY, owner_phone TEXT, text TEXT, created_at REAL, status TEXT DEFAULT 'open');
"""
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def init() -> None:
    db._conn.executescript(SCHEMA)
    if "expires_at" not in {col["name"] for col in db.q("PRAGMA table_info(knowledge)")}:
        db._conn.execute("ALTER TABLE knowledge ADD COLUMN expires_at REAL")
    db._conn.commit()


def add_file(title: str, data: bytes, filename: str, mime: str, audience: str = "customer", text: str = "") -> dict:
    safe = re.sub(r"[^\w.\-]", "_", filename) or "file"
    path = os.path.join(config.DOCS_DIR, f"kb_{int(db.now())}_{safe}")
    with open(path, "wb") as f:
        f.write(data)
    kid = db.run("INSERT INTO knowledge(title, kind, audience, path, mime, text, created_at) VALUES (?,?,?,?,?,?,?)",
                 (title, "file", audience, path, mime, text, db.now()))
    db.audit("owner", "knowledge.add", {"id": kid, "title": title, "audience": audience})
    return get(kid)


def add_fact(title: str, text: str, audience: str = "customer") -> dict:
    kid = db.run("INSERT INTO knowledge(title, kind, audience, path, mime, text, created_at) VALUES (?,?,?,?,?,?,?)",
                 (title, "fact", audience, "", "", text, db.now()))
    return get(kid)


def get(kid: int) -> dict | None:
    return db.q1("SELECT * FROM knowledge WHERE id=?", (kid,))


def all_items() -> list[dict]:
    return db.q("SELECT * FROM knowledge WHERE expires_at IS NULL OR expires_at>? ORDER BY id DESC", (db.now(),))


def confirm_rule(phone: str, draft_id: int, scope: str) -> str:
    """Apply a preview once. Today ends at midnight IST on the date it was created."""
    with db.tx():
        draft = db.q1("SELECT * FROM rule_drafts WHERE id=? AND owner_phone=? AND status='open'", (draft_id, phone))
        if not draft:
            return "This preview is closed."
        expiry = None
        if scope == "today":
            day = dt.datetime.fromtimestamp(draft["created_at"], IST).date()
            expiry = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), tzinfo=IST).timestamp()
            if expiry <= db.now():
                scope = "expired"
        db.run("UPDATE rule_drafts SET status=? WHERE id=?", (scope, draft_id))
        if scope == "cancel":
            return "Rule cancelled."
        if scope == "expired":
            return "That day has ended. Please send the rule again."
        fact = add_fact("Rule", draft["text"], "all")
        if expiry:
            db.run("UPDATE knowledge SET expires_at=? WHERE id=?", (expiry, fact["id"]))
        return "Rule saved until midnight IST." if expiry else "Rule saved for future messages."


def credit_limit(rule: str) -> float | None:
    """Parse an explicit request for owner approval above a credit threshold."""
    from brain.normalize import words_to_numbers
    words = words_to_numbers(rule)[0].lower()
    if not re.search(r"credit|udhaa?r", words) or not re.search(r"confirm|approv|pooch|puch", words):
        return None
    match = re.search(r"(?:above|over|more than)\s+(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s+(?:se\s+)?(?:upar|zyada)", words)
    return float(match.group(1) or match.group(2)) if match else None


def credit_needs_owner(amount: float) -> bool:
    limits = (credit_limit(row["text"]) for row in all_items() if row["title"] == "Rule")
    return any(limit is not None and amount > limit for limit in limits)


def delete(kid: int) -> None:
    k = get(kid)
    if k and k["path"] and os.path.exists(k["path"]):
        os.remove(k["path"])
    db.run("DELETE FROM knowledge WHERE id=?", (kid,))


def find(query: str, kind: str | None = None) -> list[dict]:
    q = (query or "").lower()
    out = []
    for k in all_items():
        if kind and k["kind"] != kind:
            continue
        score = max(fuzz.partial_ratio(k["title"].lower(), q), fuzz.token_set_ratio(k["title"].lower(), q))
        if k["text"]:
            score = max(score, fuzz.token_set_ratio(q, k["text"].lower()[:2000]) * 0.85)
        out.append({**k, "score": score})
    return sorted(out, key=lambda r: -r["score"])


def context_for_llm(limit_chars: int = 3000) -> str:
    parts = []
    for k in all_items():
        parts.append(f"[{k['title']} · for {k['audience']}] {k['text'][:600]}")
    return "\n".join(parts)[:limit_chars]


def copy_to_docs(path: str) -> str:
    dst = os.path.join(config.DOCS_DIR, os.path.basename(path))
    if os.path.abspath(path) != os.path.abspath(dst):
        shutil.copy(path, dst)
    return dst
