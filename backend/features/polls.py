"""Smart polls and tasks.

The official WhatsApp API has no polls and caps bot-managed groups at 8 people, so Bolo asks
each person individually with reply buttons, in their own language, then tallies, nudges the
silent ones, escalates to a phone call, and reports back to whoever asked.
"""
import json

import db
from core import contacts as C
from pipe import calls, messenger

POLL_OPTIONS = ["✅ Haan", "❌ Nahi", "⏰ Late"]
TASK_OPTIONS = ["✅ Done", "⏳ Later"]


# The stored option index stays the same across languages, including old polls.
LOCAL_OPTIONS = {
    "kn-IN": {"poll": ["ಹೌದು", "ಇಲ್ಲ", "ತಡವಾಗುತ್ತದೆ"], "task": ["ಮುಗಿದಿದೆ", "ನಂತರ"]},
    "hi-IN": {"poll": ["हाँ", "नहीं", "देर होगी"], "task": ["हो गया", "बाद में"]},
    "en-IN": {"poll": ["Yes", "No", "Running late"], "task": ["Done", "Later"]},
}


def reply_buttons(pid, kind, options, language):
    defaults = TASK_OPTIONS if kind == "task" else POLL_OPTIONS
    labels = LOCAL_OPTIONS.get(language, {}).get(kind, options) if options == defaults else options
    return [(f"poll:{pid}:{i}", label) for i, label in enumerate(labels)]


def resolve_people(people: list[str]) -> tuple[list[dict], list[str]]:
    """Names or @groups -> contacts. Returns (found, unknown names)."""
    found, unknown = [], []
    for p in people or []:
        if p.startswith("@"):
            for c in C.all_contacts(p[1:]):
                if c["id"] not in [f["id"] for f in found]:
                    found.append(c)
            continue
        r = C.resolve(p, role=None)
        if r["status"] == "ok" and r["contact"]["id"] not in [f["id"] for f in found]:
            found.append(r["contact"])
        elif r["status"] == "ambiguous":
            found.append(r["candidates"][0]["contact"])
        else:
            unknown.append(p)
    return found, unknown


async def create(kind: str, question: str, people: list[dict], asker_phone: str, deadline: float | None = None) -> int:
    options = TASK_OPTIONS if kind == "task" else POLL_OPTIONS
    pid = db.run("INSERT INTO polls(kind, question, options, deadline, created_by, created_at) VALUES (?,?,?,?,?,?)",
                 (kind, question, json.dumps(options, ensure_ascii=False), deadline, asker_phone, db.now()))
    shop = db.setting("shop_name")
    for c in people:
        db.run("INSERT OR IGNORE INTO poll_targets(poll_id, contact_id) VALUES (?,?)", (pid, c["id"]))
        prefix = "📋 Kaam" if kind == "task" else "❓ Sawaal"
        await messenger.say(c.get("phone") or "", f"{prefix} from {shop}: {question}", c.get("lang") or "hi-IN",
                            buttons=reply_buttons(pid, kind, options, c.get("lang")))
    return pid


def tally(pid: int) -> dict:
    poll = db.q1("SELECT * FROM polls WHERE id=?", (pid,))
    rows = db.q("SELECT t.*, c.name, c.phone FROM poll_targets t JOIN contacts c ON c.id=t.contact_id WHERE poll_id=?", (pid,))
    return {"poll": poll, "targets": rows, "answered": sum(1 for r in rows if r["answer"]), "total": len(rows)}


def summary_line(pid: int) -> str:
    t = tally(pid)
    marks = []
    for r in t["targets"]:
        ans = r["answer"] or "… no reply"
        marks.append(f"{r['name']} {ans}")
    return f"{t['answered']}/{t['total']} · " + " · ".join(marks)


async def answer(pid: int, contact: dict, option_index: int) -> None:
    poll = db.q1("SELECT * FROM polls WHERE id=?", (pid,))
    if not poll or poll["status"] != "open":
        return
    options = json.loads(poll["options"])
    if not 0 <= option_index < len(options):
        return
    choice = options[option_index]
    with db.tx() as conn:
        changed = conn.execute("UPDATE poll_targets SET answer=?, answered_at=? WHERE poll_id=? "
                               "AND contact_id=? AND (answer IS NULL OR answer!=?)",
                               (choice, db.now(), pid, contact["id"], choice))
        if not changed.rowcount:
            return
    await messenger.say(contact.get("phone") or "", f"Shukriya! Noted: {choice}", contact.get("lang") or "hi-IN", voice=False)
    asker = C.by_phone(poll["created_by"]) or {}
    t = tally(pid)
    done = t["answered"] == t["total"]
    if done:
        db.run("UPDATE polls SET status='done' WHERE id=?", (pid,))
    await messenger.say(poll["created_by"], f"{'✅ Sab ne jawab diya' if done else '🗳️ Update'} — {poll['question'][:60]}\n"
                        f"{summary_line(pid)}", asker.get("lang") or db.setting("owner_lang"), voice=done)


async def follow_up() -> None:
    """Called by the scheduler: nudge silent people, then escalate to a call, then tell the asker."""
    nudge_after = float(db.setting("nudge_after_min") or 30) * 60
    call_after = float(db.setting("call_after_min") or 60) * 60
    for poll in db.q("SELECT * FROM polls WHERE status='open'"):
        age = db.now() - poll["created_at"]
        for r in db.q("SELECT t.*, c.name, c.phone, c.lang FROM poll_targets t JOIN contacts c ON c.id=t.contact_id"
                      " WHERE poll_id=? AND answer IS NULL", (poll["id"],)):
            if age >= nudge_after and r["nudges"] == 0:
                await messenger.say(r["phone"] or "", f"🔔 Reminder: {poll['question']}", r["lang"] or "hi-IN",
                                    buttons=reply_buttons(poll["id"], poll["kind"], json.loads(poll["options"]), r["lang"]))
                db.run("UPDATE poll_targets SET nudges=1 WHERE poll_id=? AND contact_id=?", (poll["id"], r["contact_id"]))
            elif age >= call_after and not r["called"]:
                res = await calls.call(r["phone"] or "", {"name": r["name"], "question": poll["question"],
                                                          "shop": db.setting("shop_name")})
                db.run("UPDATE poll_targets SET called=1 WHERE poll_id=? AND contact_id=?", (poll["id"], r["contact_id"]))
                await messenger.say(poll["created_by"], f"📞 {r['name']} ne jawab nahi diya — call {res.get('status')}.",
                                    db.setting("owner_lang"), voice=False)
