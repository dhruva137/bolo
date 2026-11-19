"""Append-only, hash-chained khata.

Rows are never updated in place for money: corrections are new rows (kind='reversal' pointing
at the original via ref_id). Each row's hash covers the previous hash, the entry, and the
SHA-256 of the voice note that created it, so any silent edit breaks the chain.
"""
import hashlib
import json
import math

import db

KINDS = {"credit": 1, "payment": -1, "reversal": 0}


def _hash(prev: str, row: dict) -> str:
    body = json.dumps({k: row.get(k) for k in ("contact_id", "amount", "kind", "note", "due_date",
                                                "audio_sha", "actor", "ref_id", "created_at")},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev + body).encode()).hexdigest()


def add(contact_id: int, amount: float, kind: str, *, note: str = "", due_date: str = "",
        status: str = "confirmed", event_id: int | None = None, audio_sha: str = "",
        actor: str = "", ref_id: int | None = None, created_at: float | None = None) -> dict:
    amount = round(float(amount), 2)
    if kind not in KINDS or not math.isfinite(amount) or amount <= 0:
        raise ValueError("Ledger entries require a valid kind and a positive amount.")
    row = {"contact_id": contact_id, "amount": amount, "kind": kind, "note": note,
           "due_date": due_date, "audio_sha": audio_sha, "actor": actor, "ref_id": ref_id,
           "created_at": created_at or db.now()}
    with db.tx():
        last = db.q1("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1")
        prev = last["hash"] if last else "GENESIS"
        rid = db.run(
            "INSERT INTO ledger(contact_id, amount, kind, note, due_date, status, event_id, audio_sha, actor,"
            " ref_id, prev_hash, hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (contact_id, amount, kind, note, due_date, status, event_id, audio_sha, actor, ref_id,
             prev, _hash(prev, row), row["created_at"]))
        db.audit(actor, f"ledger.{kind}", {"id": rid, "contact_id": contact_id, "amount": amount})
        return get(rid)


def get(entry_id: int) -> dict | None:
    return db.q1("SELECT * FROM ledger_current WHERE id=?", (entry_id,))


def reverse(entry_id: int, actor: str, note: str = "reversed") -> dict | None:
    with db.tx():
        e = get(entry_id)
        if not e or e["kind"] == "reversal" or entry_id in reversed_ids():
            return None
        return add(e["contact_id"], e["amount"], "reversal", note=note, actor=actor, ref_id=entry_id)


def set_status(entry_id: int, status: str) -> None:
    db.run("INSERT INTO ledger_status(ledger_id,status,created_at) VALUES (?,?,?)", (entry_id, status, db.now()))


def reversed_ids() -> set[int]:
    return {r["ref_id"] for r in db.q("SELECT ref_id FROM ledger WHERE kind='reversal'")}


def effective(contact_id: int | None = None) -> list[dict]:
    """Entries that still count (not reversed, not reversal rows, not unconfirmed payment claims)."""
    rev = reversed_ids()
    sql = "SELECT * FROM ledger_current WHERE kind != 'reversal' AND status NOT IN ('claimed','rejected')"
    args: tuple = ()
    if contact_id is not None:
        sql += " AND contact_id=?"
        args = (contact_id,)
    return [e for e in db.q(sql + " ORDER BY id", args) if e["id"] not in rev]


def balance(contact_id: int) -> float:
    return round(sum(e["amount"] * KINDS[e["kind"]] for e in effective(contact_id)), 2)


def balances() -> list[dict]:
    out = []
    for c in db.q("SELECT id, name, phone, lang, credit_limit FROM contacts WHERE role='customer'"):
        entries = effective(c["id"])
        bal = round(sum(e["amount"] * KINDS[e["kind"]] for e in entries), 2)
        oldest = next((e["created_at"] for e in entries if e["kind"] == "credit"), None)
        age_days = int((db.now() - oldest) / 86400) if (oldest and bal > 0) else 0
        out.append({**c, "balance": bal, "age_days": age_days})
    return sorted(out, key=lambda r: -r["balance"])


def verify_chain() -> dict:
    prev = "GENESIS"
    for r in db.q("SELECT * FROM ledger ORDER BY id"):
        if r["prev_hash"] != prev or _hash(prev, r) != r["hash"]:
            return {"ok": False, "broken_at": r["id"]}
        prev = r["hash"]
    return {"ok": True, "entries": len(db.q("SELECT id FROM ledger"))}


def today_totals() -> dict:
    start = db.now() - (db.now() % 86400)  # UTC day; fine for a demo
    rows = [e for e in effective() if e["created_at"] >= start]
    return {
        "credit": round(sum(e["amount"] for e in rows if e["kind"] == "credit"), 2),
        "payment": round(sum(e["amount"] for e in rows if e["kind"] == "payment"), 2),
    }
