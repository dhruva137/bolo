"""The Bolo agent: listen -> understand -> verify -> act -> follow up.

Entry point: handle(phone, ...) for every inbound WhatsApp (or simulator) message.
"""
import asyncio
import datetime as dt
import hashlib
import json
import math
import os
import re

import config
import db
from brain import planner
from brain.normalize import confusable, in_words_hi, numbers_disagree, parse_date, words_to_numbers
from core import access, ledger
from core import contacts as C
from features import documents, knowledge, polls, profiles
from pipe import messenger
from voice import audio as A
from voice import docai, stt

CIRCLED = "①②③④⑤⑥⑦⑧⑨"
MONEY_TOOLS = {"add_credit", "record_payment"}
STT_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}


def _lang(c: dict | None) -> str:
    return (c or {}).get("lang") or "hi-IN"


def _owner_phone() -> str:
    o = C.owner()
    return (o or {}).get("phone") or db.setting("owner_phone")


def _keyterms() -> list[str]:
    names = [c["name"] for c in C.all_contacts()] + [a for c in C.all_contacts() for a in c["aliases"]]
    items = [r["name"] for r in db.q("SELECT name FROM catalog LIMIT 40")]
    return list(dict.fromkeys(["udhaar", "khata"] + names + items))[:50]


def _rs(x: float) -> str:
    return f"₹{x:,.0f}" if float(x).is_integer() else f"₹{x:,.2f}"


def _amount(value) -> float | None:
    """A ledger amount must be finite and positive at paise precision."""
    if isinstance(value, bool):
        return None
    try:
        number = round(float(value), 2)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _due_label(iso: str) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%a %d %b")
    except Exception:
        return ""


# ------------------------------------------------------------------------------- inbound
async def handle(phone: str, kind: str, text: str = "", audio_bytes: bytes | None = None, audio_ext: str = "ogg",
                 button: str = "", media: bytes | None = None, mime: str = "", filename: str = "",
                 profile_name: str = "", review_local: bool = False) -> dict | None:
    phone = C.normalize_phone(phone)
    contact = C.by_phone(phone)
    if not contact:
        if not C.owner():
            contact = C.upsert(profile_name or "Owner", phone, role="owner", lang=db.setting("owner_lang"), opted_in=1)
            db.set_setting("owner_phone", phone)
        else:
            contact = C.upsert(profile_name or f"New {phone[-4:]}", phone, role="customer", opted_in=1)
    elif not contact["opted_in"]:
        db.run("UPDATE contacts SET opted_in=1 WHERE id=?", (contact["id"],))  # they messaged us: service window open

    # Watch mode: the whole bot is paused, or a human has taken over this chat. Messages are still
    # recorded (voice notes still transcribed) so the manager sees everything live, but Bolo stays silent.
    watching = db.setting("bot_mode") == "paused" or bool(contact.get("paused"))

    if button:
        messenger.store_inbound(phone, "button", button)
        if not watching:
            await on_button(contact, button)
        return
    if media is not None:
        path = _save_media(media, filename or "upload", mime)
        mid = messenger.store_inbound(phone, "media", text, media=path, meta={"mime": mime})
        if not watching:
            await on_media(contact, mid, path, mime)
        return

    text_b, conf, audio_sha = "", None, ""
    if audio_bytes is not None:
        audio_sha = hashlib.sha256(audio_bytes).hexdigest()
        raw_name = f"{audio_sha[:16]}.{audio_ext}"
        with open(os.path.join(config.AUDIO_DIR, raw_name), "wb") as f:
            f.write(audio_bytes)
        dup = db.q1("SELECT id FROM events WHERE phone=? AND audio_sha=? AND created_at > ?",
                    (phone, audio_sha, db.now() - 600))
        if dup:
            if not watching:
                await messenger.say(phone, "Ye voice note pehle hi mil chuka hai ✔️", _lang(contact), voice=False)
            return
        try:
            wav = await asyncio.to_thread(A.clean, audio_bytes, audio_ext)
        except Exception:
            wav = audio_bytes
        a, b = await stt.hear_twice(wav, _keyterms())
        text = a.text or b.text
        text_b = b.text if a.text else ""
        conf = b.confidence
        if a.language in STT_LANGS and (a.confidence or 0) >= 0.6 and a.language != contact["lang"] and contact["role"] != "owner":
            db.run("UPDATE contacts SET lang=? WHERE id=?", (a.language, contact["id"]))
            contact["lang"] = a.language
        meta = {"primary_stt": a.engine if a.text or a.engine == "whisper-local" else (b.engine if b.text else None),
                "secondary_stt": b.engine if a.text and b.text else None,
                "engine_a": a.text, "engine_b": b.text, "lang": a.language,
                "lang_prob": a.confidence, "conf_b": b.confidence, "audio_sha": audio_sha}
        needs_review = review_local and not watching and (a.engine == "whisper-local" or not text)
        if needs_review:
            meta["review_status"] = "pending"
        message_id = messenger.store_inbound(phone, "voice", text or "(unclear)", media=f"/audio/{raw_name}", meta=meta)
        if watching:
            return
        if needs_review:
            return {"message_id": message_id, "phone": phone, "text": text}
        if not (text or "").strip():
            await messenger.say(phone, "🙏 Kuch sunai nahi diya — phir se boliye?", _lang(contact))
            return
    else:
        messenger.store_inbound(phone, "text", text)
        # A customer typing plain English gets replies in English (voice notes are detected by the speech engine).
        if contact["role"] == "customer" and contact.get("lang") != "en-IN" and _looks_english(text):
            db.run("UPDATE contacts SET lang='en-IN' WHERE id=?", (contact["id"],))
            contact["lang"] = "en-IN"
        if watching:
            return
    await _act_on_transcript(contact, text, text_b, conf, audio_sha)


def _looks_english(text: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    common = {"the", "is", "are", "how", "what", "please", "you", "do", "can", "much", "my", "i", "send", "want", "today", "when", "your"}
    return text.isascii() and len(words) >= 3 and sum(w in common for w in words) >= 2


async def review_voice(phone: str, message_id: int, text: str, discard: bool) -> str:
    """The recording and engine output remain available after the speaker corrects the text."""
    contact = C.by_phone(phone)
    if not contact:
        raise ValueError("Unknown speaker")
    if not discard and (db.setting("bot_mode") == "paused" or contact.get("paused")):
        raise ValueError("Resume the bot before using this transcript")
    with db.tx() as connection:
        row = connection.execute("SELECT meta FROM messages WHERE id=? AND phone=? AND direction='in' AND kind='voice'",
                                 (message_id, phone)).fetchone()
        meta = json.loads(row["meta"]) if row else {}
        status = meta.get("review_status")
        if not status:
            raise ValueError("This speaker has no review for that recording")
        if status != "pending":
            return status
        meta["review_status"] = "discarded" if discard else "processing"
        if not discard:
            meta["reviewed_text"] = text
        connection.execute("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), message_id))
    if discard:
        return "discarded"
    try:
        await _act_on_transcript(contact, text, "", None, meta["audio_sha"])
    except Exception:
        meta["review_status"] = "failed"
        raise
    else:
        meta["review_status"] = "used"
    finally:
        db.run("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), message_id))
    return "used"


async def _act_on_transcript(contact: dict, text: str, text_b: str, conf: float | None, audio_sha: str) -> None:
    phone = contact["phone"]
    reply = text.strip().lower().strip(".!,?।").strip()
    affirmations = {"haan", "han", "yes", "sahi hai", "हाँ", "हां", "ಹೌದು", "haudu"}
    if reply in affirmations or reply in {"1", "2", "3"}:
        last = db.q1("SELECT buttons FROM messages WHERE phone=? AND direction='out' AND kind!='voice' "
                     "ORDER BY id DESC LIMIT 1", (phone,))
        buttons = json.loads((last or {}).get("buttons") or "[]")
        if reply in affirmations:
            chosen = next((bid for bid, _ in buttons if bid.startswith(("ok:", "agree:"))), None)
        else:
            idx = int(reply) - 1
            chosen = buttons[idx][0] if idx < len(buttons) else None
        if chosen:
            await on_button(contact, chosen, audio_sha)
            return

    # First words from the owner configure the bot: "I run a school in Jayanagar with 300 students…"
    if contact["role"] == "owner" and db.setting("onboarded") != "1":
        prof = profiles.apply(text)
        feats = ", ".join(profiles.FEATURES[f][0] for f in prof["features"] if f in profiles.FEATURES and not profiles.FEATURES[f][2])
        await messenger.say(phone, f"🙏 Namaste! Bolo is set up for *{prof['name']}* ({prof['label']}).\n"
                            f"I'll call your people: {', '.join(prof['roles'][r] for r in ('customer', 'staff', 'supplier'))}.\n"
                            f"Extra features on: {feats or 'core only'}.\nTry saying: \"{prof['hints'][0]}\"\n"
                            f"Customise everything at {config.PUBLIC_BASE_URL}", _lang(contact))
        return

    greetings = {"hi", "hii", "hiii", "hello", "helo", "hey", "namaste", "namaskar", "namaskara", "hai",
                 "नमस्ते", "नमस्कार", "ನಮಸ್ಕಾರ", "ನಮಸ್ತೆ", "start"}
    if reply in greetings or re.fullmatch(r"(h+i+|h+e+y+|h+e+l+o+|hello+ bolo|hi+ bolo|namaste+|namaskara?)( (bhaiya|anna|sir|ji))?", reply):
        if contact["role"] == "owner":
            msg = ("🙏 Namaste! Main Bolo hoon — aapka hisaab-kitaab ka saathi.\n"
                   "Voice note bhejiye, jaise: 'Ramesh 450 ka saman liya, Shanivar dega' "
                   "ya 'Lakshmi ne 200 diye'. Photo ya bill bhi bhej sakte hain.")
        else:
            msg = "🙏 Namaste! Main Bolo hoon. Apna sawaal voice note ya message mein bhejiye."
        await messenger.say(phone, msg, _lang(contact), voice=False)
        return

    event_id = db.run("INSERT INTO events(phone, contact_id, kind, audio_sha, transcript, transcript_b, lang, created_at)"
                      " VALUES (?,?,?,?,?,?,?,?)", (phone, contact["id"], "voice" if audio_sha else "text", audio_sha,
                                                    text, text_b, contact["lang"], db.now()))

    editing = db.q1("SELECT * FROM pending WHERE phone=? AND status='editing' ORDER BY id DESC LIMIT 1", (phone,))
    if editing:
        await apply_correction(contact, editing, text)
        return

    actions, provider = planner.plan(text, contact["role"], text_b)
    db.run("UPDATE events SET plan=? WHERE id=?", (json.dumps({"provider": provider, "actions": actions},
                                                              ensure_ascii=False), event_id))
    if not actions:
        if contact["role"] == "customer":
            await messenger.say(phone, "🤔 Samajh nahi aaya. Aap pooch sakte hain: 'mera kitna baaki hai', 'atta kitne ka hai', "
                                "ya order boliye: '2 kilo cheeni aur ek doodh bhejo'.", _lang(contact))
            return
        await messenger.say(phone, "🤔 Samajh nahi aaya. Jaise boliye: 'Ramesh 450 udhaar' ya 'Lakshmi ne 200 diye'.",
                            _lang(contact))
        return
    await execute(contact, actions, event_id, audio_sha, text, text_b, conf)


def _save_media(data: bytes, name: str, mime: str) -> str:
    ext = os.path.splitext(name)[1] or {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}.get(mime, "")
    path = os.path.join(config.DOCS_DIR, f"in_{hashlib.sha256(data).hexdigest()[:12]}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


# ------------------------------------------------------------------------------- execute
async def execute(contact: dict, actions: list[dict], event_id: int, audio_sha: str, text: str, text_b: str,
                  conf: float | None) -> None:
    phone, role = contact["phone"], contact["role"]
    money_items: list[dict] = []
    for act in actions:
        tool, args = act.get("tool"), act.get("args") or {}
        if not access.can(role, tool):
            await messenger.say(phone, f"⛔ Aapke role ({profiles.role_label(role)}) ko '{tool}' ki permission nahi hai.",
                                _lang(contact), voice=False)
            continue
        need = profiles.TOOL_FEATURE.get(tool)
        if need and not profiles.is_on(need):
            await messenger.say(phone, f"'{profiles.FEATURES[need][0]}' feature band hai. Console → Features mein on karein.",
                                _lang(contact), voice=False)
            continue
        if tool in MONEY_TOOLS:
            money_items.append(_money_item(tool, args, text, text_b, conf))
            continue
        reason = access.needs_owner_approval(role, tool, args)
        handler = TOOLS.get(tool)
        if handler:
            await handler(contact, args, event_id=event_id, audio_sha=audio_sha, approval_reason=reason, text=text)
    if money_items:
        await _money_flow(contact, money_items, event_id, audio_sha)


def _money_item(tool: str, args: dict, text: str, text_b: str, conf: float | None) -> dict:
    name = str(args.get("name") or "").strip()
    value = args.get("amount")
    amount = _amount(value)
    if amount is None and isinstance(value, str) and value.isalpha():
        amount = _amount((words_to_numbers(value)[1] or [None])[0])
    item = {"tool": tool, "name_said": name, "amount": amount, "due": parse_date(str(args.get("due") or "")),
            "items": args.get("items") or "", "contact_id": None, "issues": [], "alt": []}
    res = C.resolve(name, role="customer") if name else {"status": "new", "candidates": []}
    if res["status"] == "ok":
        item["contact_id"] = res["contact"]["id"]
    elif res["status"] == "ambiguous":
        item["issues"].append("ambiguous_name")
        item["alt"] = [c["contact"]["id"] for c in res["candidates"]][:2]
    else:
        item["issues"].append("new_name" if name else "no_name")
    if amount is None:
        item["issues"].append("no_amount")
    else:
        mism = numbers_disagree(text, text_b)
        alt = _amount(args.get("amount_alt"))
        if alt is not None and abs(alt - amount) > 0.01:
            item["issues"].append("engines_disagree")
            item["alt_amount"] = float(alt)
        elif mism and any(abs(a - amount) < 0.01 or abs(b - amount) < 0.01 for a, b in mism):
            a, b = next((a, b) for a, b in mism if abs(a - amount) < 0.01 or abs(b - amount) < 0.01)
            item["issues"].append("engines_disagree")
            item["alt_amount"] = b if abs(a - amount) < 0.01 else a
        if confusable(amount):
            item["issues"].append("confusable")
    if conf is not None and conf < 0.45:
        item["issues"].append("low_confidence")
    if item["contact_id"] and tool == "add_credit" and amount:
        c = C.get(item["contact_id"])
        if c and c["credit_limit"] and ledger.balance(c["id"]) + amount > c["credit_limit"]:
            item["issues"].append("over_limit")
    if tool == "add_credit" and amount and knowledge.credit_needs_owner(amount):
        item["issues"].append("owner_rule")
    return item


def _line(i: int, it: dict) -> str:
    c = C.get(it["contact_id"]) if it["contact_id"] else None
    who = c["name"] if c else (it["name_said"] or "?")
    sign = "+" if it["tool"] == "add_credit" else "−"
    kind = "udhaar" if it["tool"] == "add_credit" else "jama"
    amt = f"{_rs(it['amount'])} ({in_words_hi(it['amount'])})" if it["amount"] is not None else "₹?"
    due = f" · due {_due_label(it['due'])}" if it.get("due") else ""
    warn = {"ambiguous_name": "kaunsa?", "new_name": "naya customer?", "no_name": "kiska?", "no_amount": "kitna?",
            "over_limit": "limit cross!", "owner_rule": "shop rule: owner confirmation",
            "low_confidence": "awaaz saaf nahi"}
    if "engines_disagree" in it["issues"]:
        warn["engines_disagree"] = f"{_rs(it['amount'])} ya {_rs(it['alt_amount'])}?"
    flags = [warn[i] for i in it["issues"] if i in warn]
    return f"{CIRCLED[i] if i < 9 else '•'} {who} {sign}{amt} {kind}{due}" + (f"  ⚠️ {', '.join(flags)}" if flags else "")


def _buttons(pid: int, items: list[dict]) -> list[tuple[str, str]]:
    for idx, it in enumerate(items):
        if "ambiguous_name" in it["issues"]:
            btns = [(f"pick:{pid}:{idx}:{cid}", C.label(C.get(cid))) for cid in it["alt"]]
            return btns + [(f"new:{pid}:{idx}", f"➕ Naya {it['name_said']}"[:20])]
        if "engines_disagree" in it["issues"]:
            return [(f"num:{pid}:{idx}:{it['amount']:g}", _rs(it["amount"])),
                    (f"num:{pid}:{idx}:{it['alt_amount']:g}", _rs(it["alt_amount"])), (f"redo:{pid}", "🔁 Phir se")]
        if "no_name" in it["issues"] or "no_amount" in it["issues"]:
            return [(f"fix:{pid}", "✏️ Batao"), (f"redo:{pid}", "🔁 Phir se")]
    return [(f"ok:{pid}", "✅ Sahi"), (f"fix:{pid}", "✏️ Badlo"), (f"redo:{pid}", "🔁 Phir se")]


async def _show_card(contact: dict, pid: int) -> None:
    p = db.q1("SELECT * FROM pending WHERE id=?", (pid,))
    items = json.loads(p["actions"])
    head = "🧾 Confirm karein:" if all(not it["issues"] or it["issues"] == ["confusable"] for it in items) else "⚠️ Check karein:"
    body = head + "\n" + "\n".join(_line(i, it) for i, it in enumerate(items))
    await messenger.say(contact["phone"], body, _lang(contact), buttons=_buttons(pid, items))


async def _money_flow(contact: dict, items: list[dict], event_id: int, audio_sha: str) -> None:
    for it in items:
        it["audio_sha"] = audio_sha
        it["event_id"] = event_id
        # staff entries above the threshold go to the owner first
        if contact["role"] != "owner" and it["amount"] and access.needs_owner_approval(contact["role"], it["tool"], {"amount": it["amount"]}):
            it["issues"].append("needs_owner")
    threshold = float(db.setting("readback_amount") or 500)
    risky = any(it["issues"] or (it["amount"] or 0) >= threshold for it in items)
    if db.setting("confirm_money") == "always" or risky:
        pid = db.run("INSERT INTO pending(event_id, phone, actions, reasons, created_at) VALUES (?,?,?,?,?)",
                     (event_id, contact["phone"], json.dumps(items, ensure_ascii=False),
                      json.dumps([i for it in items for i in it["issues"]]), db.now()))
        await _show_card(contact, pid)
    else:
        await _commit(contact, items)


async def _commit(contact: dict, items: list[dict]) -> None:
    lines = []
    for it in items:
        if not it["contact_id"]:
            if not it["name_said"]:
                continue
            it["contact_id"] = C.upsert(it["name_said"].title(), role="customer")["id"]
        if it["amount"] is None:
            continue
        rule_approval = (contact["role"] != "owner" and it["tool"] == "add_credit"
                         and knowledge.credit_needs_owner(it["amount"]))
        if rule_approval or access.needs_owner_approval(contact["role"], it["tool"], {"amount": it["amount"]}):
            await _ask_owner_approval(contact, {"type": "money", "item": it},
                                      f"{contact['name']} wants: {_line(0, {**it, 'issues': []})}")
            lines.append(f"⏳ Owner approval ke liye bheja: {_rs(it['amount'])}")
            continue
        kind = "credit" if it["tool"] == "add_credit" else "payment"
        e = ledger.add(it["contact_id"], it["amount"], kind, note=str(it.get("items") or ""), due_date=it.get("due") or "",
                       event_id=it.get("event_id"), audio_sha=it.get("audio_sha", ""), actor=contact["phone"])
        cust = C.get(it["contact_id"])
        if it["name_said"] and C.romanize(it["name_said"]) != C.romanize(cust["name"]):
            C.add_alias(cust["id"], it["name_said"])  # learn "Rameshanna" after one confirmation
        bal = ledger.balance(cust["id"])
        lines.append(f"✅ {cust['name']} {'+' if kind == 'credit' else '−'}{_rs(it['amount'])} · baaki {_rs(bal)}")
        await _notify_customer(cust, e, bal)
    if lines:
        await messenger.say(contact["phone"], "Likh liya:\n" + "\n".join(lines), _lang(contact))


async def _notify_customer(cust: dict, e: dict, bal: float) -> None:
    if not profiles.is_on("customer_loop") or not cust.get("phone") or not cust.get("opted_in"):
        return
    shop = db.setting("shop_name")
    if e["kind"] == "credit":
        due = f", due {_due_label(e['due_date'])}" if e["due_date"] else ""
        word = profiles.profile()["dues_word"]
        btns = [(f"agree:{e['id']}", "👍 Sahi hai"), (f"dispute:{e['id']}", "❌ Galat hai")]
        if profiles.is_on("upi_pay"):
            btns.append((f"pay:{e['id']}", "💸 Pay now"))
        await messenger.say(cust["phone"], f"{shop}: {_rs(e['amount'])} {word} likha gaya{due}. Total baaki {_rs(bal)}. Sahi hai?",
                            _lang(cust), buttons=btns)
    else:
        await messenger.say(cust["phone"], f"{shop}: {_rs(e['amount'])} mil gaya, shukriya! Baaki {_rs(bal)}.", _lang(cust))


# ------------------------------------------------------------------------------- corrections
async def apply_correction(contact: dict, p: dict, text: str) -> None:
    items = json.loads(p["actions"])
    norm, nums = words_to_numbers(text)
    names = planner._names_in(norm)
    target = 0
    if names:
        for i, it in enumerate(items):
            if it["contact_id"] and C.get(it["contact_id"])["name"] in names:
                target = i
    it = items[target]
    corrected = _amount(nums[-1]) if nums else None
    if corrected is not None:
        it["amount"] = corrected
        it["issues"] = [i for i in it["issues"] if i not in ("no_amount", "engines_disagree", "confusable", "low_confidence")]
    if names and not it["contact_id"]:
        r = C.resolve(names[0])
        if r["status"] == "ok":
            it["contact_id"] = r["contact"]["id"]
            it["issues"] = [i for i in it["issues"] if i not in ("ambiguous_name", "new_name", "no_name")]
    db.run("UPDATE pending SET actions=?, status='open' WHERE id=?", (json.dumps(items, ensure_ascii=False), p["id"]))
    await _show_card(contact, p["id"])


def _last_entry(actor: str) -> dict | None:
    rev = ledger.reversed_ids()
    for e in db.q("SELECT * FROM ledger WHERE actor=? AND kind!='reversal' ORDER BY id DESC LIMIT 5", (actor,)):
        if e["id"] not in rev and db.now() - e["created_at"] < 600:
            return e
    return None


async def t_correct_last(contact, args, **kw):
    e = _last_entry(contact["phone"])
    amount = _amount(args.get("amount"))
    if not e or amount is None:
        await messenger.say(contact["phone"], "Pichhli entry nahi mili (10 min ke andar). Poori baat phir se boliye.", _lang(contact))
        return
    with db.tx():
        if not ledger.reverse(e["id"], contact["phone"], note=f"corrected to {amount}"):
            return
        new = ledger.add(e["contact_id"], amount, e["kind"], note=e["note"], due_date=e["due_date"], event_id=kw.get("event_id"),
                         audio_sha=kw.get("audio_sha", ""), actor=contact["phone"], ref_id=e["id"])
    cust = C.get(e["contact_id"])
    await messenger.say(contact["phone"], f"✏️ Theek kiya: {cust['name']} {_rs(e['amount'])} → {_rs(new['amount'])} · baaki {_rs(ledger.balance(cust['id']))}",
                        _lang(contact))


async def t_undo_last(contact, args, **kw):
    e = _last_entry(contact["phone"])
    if not e:
        await messenger.say(contact["phone"], "Hatane ke liye pichhli entry nahi mili (10 min).", _lang(contact))
        return
    ledger.reverse(e["id"], contact["phone"], note="undo by voice")
    cust = C.get(e["contact_id"])
    await messenger.say(contact["phone"], f"↩️ Hata diya: {cust['name']} {_rs(e['amount'])}. Record mein dikhega (audit).", _lang(contact))


# ------------------------------------------------------------------------------- buttons
async def on_button(contact: dict, bid: str, audio_sha: str = "") -> None:
    phone = contact["phone"]
    # A button ID can come from a stale client or an unexpected provider payload.
    simple = r"(?:ok|fix|redo|agree|dispute|pay|keep|change|recv|norecv|approve|reject):[0-9]{1,18}"
    choice = r"(?:poll|new):[0-9]{1,18}:[0-9]{1,3}|pick:[0-9]{1,18}:[0-9]{1,3}:[0-9]{1,18}"
    number = r"num:[0-9]{1,18}:[0-9]{1,3}:[0-9.eE+\-]{1,24}"
    media = r"media:[0-9]{1,18}:(?:template|supplier|ignore)"
    rule = r"rule:[0-9]{1,18}:(?:today|ongoing|cancel)"
    order = r"ord:[0-9]{1,18}:(?:ok|edit|other|ready|credit)"
    if not isinstance(bid, str) or not re.fullmatch("|".join((simple, choice, number, media, rule, order)), bid):
        await messenger.say(phone, "Ye button purana hai.", _lang(contact), voice=False)
        return
    parts = bid.split(":")
    kind = parts[0]
    if kind == "ord":
        await _order_button(contact, int(parts[1]), parts[2])
        return
    if kind == "rule":
        if contact["role"] == "owner":
            message = knowledge.confirm_rule(phone, int(parts[1]), parts[2])
            await messenger.say(phone, message, _lang(contact), voice=False)
        return
    if kind in ("ok", "fix", "redo", "pick", "new", "num"):
        p = db.q1("SELECT * FROM pending WHERE id=? AND phone=?", (int(parts[1]), phone))
        if not p or p["status"] in ("done", "cancelled"):
            await messenger.say(phone, "Ye entry pehle hi ho chuki hai.", _lang(contact), voice=False)
            return
        items = json.loads(p["actions"])
        if bid not in {button_id for button_id, _ in _buttons(p["id"], items)}:
            await _show_card(contact, p["id"])
            return
        if kind == "ok":
            db.run("UPDATE pending SET status='done' WHERE id=?", (p["id"],))
            await _commit(contact, items)
            return
        if kind == "fix":
            db.run("UPDATE pending SET status='editing' WHERE id=?", (p["id"],))
            await messenger.say(phone, "✏️ Boliye kya badalna hai — jaise 'nahi, 540' ya 'Ramesh Kumar'.", _lang(contact))
            return
        if kind == "redo":
            db.run("UPDATE pending SET status='cancelled' WHERE id=?", (p["id"],))
            await messenger.say(phone, "🔁 Theek hai, phir se boliye.", _lang(contact))
            return
        idx = int(parts[2])
        it = items[idx]
        if kind == "pick":
            it["contact_id"] = int(parts[3])
            it["issues"] = [i for i in it["issues"] if i != "ambiguous_name"]
        elif kind == "new":
            it["contact_id"] = C.upsert((it["name_said"] or "Customer").title(), role="customer")["id"]
            it["issues"] = [i for i in it["issues"] if i not in ("ambiguous_name", "new_name")]
        elif kind == "num":
            it["amount"] = float(parts[3])
            it["issues"] = [i for i in it["issues"] if i not in ("engines_disagree", "confusable")]
        db.run("UPDATE pending SET actions=? WHERE id=?", (json.dumps(items, ensure_ascii=False), p["id"]))
        await _show_card(contact, p["id"])
        return
    if kind == "poll":
        await polls.answer(int(parts[1]), contact, int(parts[2]))
        return
    if kind in ("agree", "dispute", "pay"):
        await _customer_button(contact, kind, int(parts[1]), audio_sha)
        return
    if kind in ("keep", "change"):
        await _resolve_dispute(contact, kind, int(parts[1]))
        return
    if kind in ("recv", "norecv"):
        e = ledger.get(int(parts[1]))
        if contact["role"] == "owner" and e and e["kind"] == "payment" and e["status"] == "claimed":
            ledger.set_status(e["id"], "confirmed" if kind == "recv" else "rejected")
            cust = C.get(e["contact_id"])
            msg = f"✅ {cust['name']} ka {_rs(e['amount'])} confirm." if kind == "recv" else f"❌ {cust['name']} ka {_rs(e['amount'])} nahi mila — note kiya."
            await messenger.say(phone, msg + f" Baaki {_rs(ledger.balance(cust['id']))}", _lang(contact), voice=False)
            await messenger.say(cust["phone"] or "", f"{db.setting('shop_name')}: payment {_rs(e['amount'])} "
                                f"{'confirm ho gaya ✅' if kind == 'recv' else 'abhi tak nahi mila. Please check karein.'}", _lang(cust))
        return
    if kind in ("approve", "reject"):
        await _approval(contact, kind, int(parts[1]))
        return
    if kind == "media":
        await _media_choice(contact, int(parts[1]), parts[2])
        return
    await messenger.say(phone, "Ye button purana hai.", _lang(contact), voice=False)


# ------------------------------------------------------------------------------- customer loop
async def _customer_button(cust: dict, kind: str, lid: int, audio_sha: str = "") -> None:
    e = ledger.get(lid)
    if not e or e["contact_id"] != cust["id"] or e["kind"] != "credit" or lid in ledger.reversed_ids():
        return
    owner = _owner_phone()
    if kind == "agree":
        if e["status"] == "agreed":
            return
        ledger.set_status(lid, "agreed")
        db.run("INSERT INTO claims(ledger_id, contact_id, kind, amount, audio_sha, created_at, status) "
               "VALUES (?,?,?,?,?,?,'closed')", (lid, cust["id"], "agree", e["amount"], audio_sha, db.now()))
        await messenger.say(cust["phone"], "👍 Shukriya! Record ho gaya.", _lang(cust), voice=False)
        await messenger.say(owner, f"👍 {cust['name']} ne {_rs(e['amount'])} confirm kiya.", db.setting("owner_lang"), voice=False)
    elif kind == "dispute":
        # The customer's next voice note ("galat, 350 tha") becomes the dispute with their own words as evidence.
        await messenger.say(cust["phone"], "Theek hai. Voice note mein bataiye kya galat hai — sahi amount kya tha?", _lang(cust))
    elif kind == "pay":
        await _send_pay(cust, ledger.balance(cust["id"]) or e["amount"])


async def _send_pay(cust: dict, amount: float) -> None:
    if not db.setting("upi_id"):
        await messenger.say(cust["phone"], f"Total baaki {_rs(amount)}. Dukaan par cash/UPI se de sakte hain.", _lang(cust))
        return
    await messenger.send_link(cust["phone"], f"💸 {db.setting('shop_name')} ko {_rs(amount)} pay karein (UPI):",
                              messenger.payment_url(cust["id"], amount))


async def _resolve_dispute(owner: dict, kind: str, claim_id: int) -> None:
    if owner["role"] != "owner":
        return
    with db.tx():
        cl = db.q1("SELECT * FROM claims WHERE id=? AND kind='dispute' AND status='open'", (claim_id,))
        if not cl:
            return
        e = ledger.get(cl["ledger_id"])
        cust = C.get(cl["contact_id"])
        db.run("UPDATE claims SET status='closed' WHERE id=?", (claim_id,))
        if e["id"] in ledger.reversed_ids():
            return
        if kind == "change" and _amount(cl["amount"]):
            ledger.reverse(e["id"], owner["phone"], note=f"dispute #{claim_id}")
            ledger.add(e["contact_id"], cl["amount"], e["kind"], note=e["note"], due_date=e["due_date"],
                       actor=owner["phone"], ref_id=e["id"], audio_sha=cl["audio_sha"] or "")
            msg = f"{_rs(e['amount'])} → {_rs(cl['amount'])} kar diya"
        else:
            ledger.set_status(e["id"], "confirmed")
            msg = f"{_rs(e['amount'])} hi rakha"
    bal = ledger.balance(cust["id"])
    await messenger.say(owner["phone"], f"✔️ {cust['name']}: {msg}. Baaki {_rs(bal)}", _lang(owner), voice=False)
    await messenger.say(cust["phone"] or "", f"{db.setting('shop_name')}: aapka sawaal dekha — {msg}. Total baaki {_rs(bal)}.", _lang(cust))


# ------------------------------------------------------------------------------- customer tools
async def t_query_own_balance(c, args, **kw):
    bal = ledger.balance(c["id"])
    last = ledger.effective(c["id"])[-3:]
    hist = "\n".join(f"• {dt.datetime.fromtimestamp(e['created_at']).strftime('%d %b')}: "
                     f"{'+' if e['kind'] == 'credit' else '−'}{_rs(e['amount'])}" for e in last)
    btns = [(f"pay:{last[-1]['id']}", "💸 Pay now")] if (bal > 0 and last) else None
    await messenger.say(c["phone"], f"{db.setting('shop_name')}: aapka total baaki {_rs(bal)}.\n{hist}", _lang(c), buttons=btns)


async def t_request_bill(c, args, **kw):
    """Customer asks for their bill to pay it: build the statement PDF from their own khata, send it to them
    directly (their own data, so no approval) with a UPI Pay-now button, and tell the shop."""
    entries = ledger.effective(c["id"])
    bal = ledger.balance(c["id"])
    if not entries:
        await messenger.say(c["phone"], "🙏 Aapke khaate mein abhi koi entry nahi hai.", _lang(c))
        return
    items = [{"name": f"{dt.datetime.fromtimestamp(e['created_at']).strftime('%d %b')} {'udhaar' if e['kind'] == 'credit' else 'jama'}"
                      + (f" · {e['note']}" if e.get("note") and not e["note"].startswith("claimed") else ""),
              "qty": 1, "rate": e["amount"] if e["kind"] == "credit" else -e["amount"]} for e in entries]
    doc = documents.make("statement", {"to_name": c["name"], "items": items, "note": "Statement requested by the customer"}, c["id"])
    await messenger.send_file(c["phone"], doc["path"], doc["filename"], f"📄 {db.setting('shop_name') or 'Shop'}: aapka bill / statement", doc["mime"])
    last = [e for e in entries if e["kind"] == "credit"]
    btns = [(f"pay:{last[-1]['id']}", "💸 Pay now (UPI)")] if bal > 0 and last else None
    await messenger.say(c["phone"], f"Total baaki: *{_rs(bal)}* ({len(entries)} entries). Pay now dabaiye, UPI se turant ho jayega.",
                        _lang(c), buttons=btns)
    await messenger.say(_owner_phone(), f"📄 {c['name']} ne bill maanga, bhej diya ({_rs(bal)} baaki).", db.setting("owner_lang"), voice=False)


async def t_promise(c, args, **kw):
    when = parse_date(str(args.get("when") or ""))
    amount = args.get("amount") or ledger.balance(c["id"])
    db.run("INSERT INTO claims(contact_id, kind, amount, date, text, audio_sha, created_at) VALUES (?,?,?,?,?,?,?)",
           (c["id"], "promise", amount, when, kw.get("text", ""), kw.get("audio_sha", ""), db.now()))
    if when:
        due_at = dt.datetime.combine(dt.date.fromisoformat(when), dt.time(9, 0)).timestamp()
        db.run("INSERT INTO reminders(contact_id, text, due_at, created_at) VALUES (?,?,?,?)",
               (c["id"], f"🙏 Yaad dilana: aaj {db.setting('shop_name')} ko {_rs(float(amount))} dene ka vaada tha.", due_at, db.now()))
    await messenger.say(c["phone"], f"👍 Noted: {_due_label(when) or 'jaldi'} — {_rs(float(amount))}. Shukriya!", _lang(c))
    await messenger.say(_owner_phone(), f"🤝 {c['name']}: '{kw.get('text', '')[:80]}' → vaada {_due_label(when) or '?'} ({_rs(float(amount))})",
                        db.setting("owner_lang"), voice=False)


async def t_dispute(c, args, **kw):
    e = next((x for x in reversed(ledger.effective(c["id"])) if x["kind"] == "credit"), None)
    if not e:
        await messenger.say(c["phone"], "Aapke naam koi udhaar entry nahi hai.", _lang(c))
        return
    amount = _amount(args.get("amount"))
    ledger.set_status(e["id"], "disputed")
    cid = db.run("INSERT INTO claims(ledger_id, contact_id, kind, amount, text, audio_sha, created_at) VALUES (?,?,?,?,?,?,?)",
                 (e["id"], c["id"], "dispute", amount, kw.get("text", ""), kw.get("audio_sha", ""), db.now()))
    await messenger.say(c["phone"], "📝 Aapki baat dukaan tak pahucha di. Jawab jaldi aayega.", _lang(c))
    btns = [(f"keep:{cid}", f"Keep {_rs(e['amount'])}"[:20])]
    if amount:
        btns.append((f"change:{cid}", f"Change {_rs(float(amount))}"[:20]))
    await messenger.say(_owner_phone(), f"⚠️ Dispute: {c['name']} kehte hain '{kw.get('text', '')[:100]}'\n"
                        f"Entry: {_rs(e['amount'])} ({dt.datetime.fromtimestamp(e['created_at']).strftime('%d %b')}). "
                        f"Dono voice notes console mein.", db.setting("owner_lang"), buttons=btns)


async def t_paid_claim(c, args, **kw):
    amount = _amount(args.get("amount"))
    if amount is None:
        await messenger.say(c["phone"], "Kitna pay kiya? Amount boliye.", _lang(c))
        return
    e = ledger.add(c["id"], amount, "payment", note=f"claimed: {args.get('mode') or ''}", status="claimed",
                   audio_sha=kw.get("audio_sha", ""), actor=c["phone"])
    await messenger.say(c["phone"], f"🙏 Noted {_rs(amount)}. Dukaan confirm karegi.", _lang(c))
    await messenger.say(_owner_phone(), f"💸 {c['name']} keh rahe hain {_rs(amount)} de diya. Mila?", db.setting("owner_lang"),
                        buttons=[(f"recv:{e['id']}", "✅ Mila"), (f"norecv:{e['id']}", "❌ Nahi mila")])


# ---- Customer orders: analyse the voice note, price it from the catalog, ask the customer to confirm.
# Business-side settings (Bolo Chat business menu / console Settings):
#   order_confirm = "1" ask the customer to confirm (default) | "0" accept straight away
#   order_eta     = promised ready time shown to the customer, e.g. "30 min"
def _orders_table() -> None:
    db.run("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, contact_id INTEGER, phone TEXT, items TEXT, "
           "total REAL, status TEXT, created_at REAL)")


def _price_items(items: list) -> list[dict]:
    """Match each spoken item to the catalog (name or alias, fuzzy) and price it."""
    from rapidfuzz import fuzz, process
    cat = db.q("SELECT * FROM catalog")
    keys = {}
    for r in cat:
        for k in [r["name"], *json.loads(r["aliases"] or "[]")]:
            keys[k.lower()] = r
    out = []
    for it in items or []:
        name = str((it or {}).get("name") or "").strip()
        if not name:
            continue
        try:
            qty = float((it or {}).get("qty") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        hit = process.extractOne(name.lower(), list(keys), scorer=fuzz.WRatio) if keys else None
        row = keys[hit[0]] if hit and hit[1] >= 75 else None
        out.append({"name": row["name"] if row else name, "qty": qty, "unit": row["unit"] if row else "",
                    "price": row["price"] if row else 0.0, "amount": round(qty * row["price"], 2) if row else 0.0})
    return out


def _order_text(items: list[dict], total: float) -> str:
    lines = "\n".join(f"• {i['qty']:g} {i['unit'] or 'x'} {i['name']}" + (f" — {_rs(i['amount'])}" if i["amount"] else " — (rate dukaan batayegi)")
                      for i in items)
    return f"{lines}\n*Total: {_rs(total)}*" if total else lines


async def t_create_order(c, args, **kw):
    _orders_table()
    items = _price_items(args.get("items") or [])
    if not items:
        await messenger.say(c["phone"], "🛒 Kya chahiye? Item aur quantity boliye, jaise: '2 kilo atta aur ek Fortune oil'.", _lang(c))
        return
    total = round(sum(i["amount"] for i in items), 2)
    oid = db.run("INSERT INTO orders(contact_id, phone, items, total, status, created_at) VALUES (?,?,?,?,?,?)",
                 (c["id"], c["phone"], json.dumps(items, ensure_ascii=False), total, "draft", db.now()))
    if db.setting("order_confirm") == "0":
        await _order_confirmed(c, oid)
        return
    await messenger.say(c["phone"], f"🛒 Aapka order samjha:\n{_order_text(items, total)}\n\nConfirm karein?", _lang(c),
                        buttons=[(f"ord:{oid}:ok", "✅ Order confirm"), (f"ord:{oid}:edit", "✏️ Badlo"),
                                 (f"ord:{oid}:other", "💬 Kuch aur")])


async def _order_confirmed(c, oid: int) -> None:
    o = db.q1("SELECT * FROM orders WHERE id=?", (oid,))
    db.run("UPDATE orders SET status='confirmed' WHERE id=?", (oid,))
    items = json.loads(o["items"])
    eta = db.setting("order_eta") or "30 min"
    await messenger.say(c["phone"], f"✅ Order #{oid} confirm! {eta} mein ready hoga. Dhanyavaad 🙏", _lang(c))
    await messenger.say(_owner_phone(), f"🛒 *New order #{oid}* — {c['name']}\n{_order_text(items, o['total'])}",
                        db.setting("owner_lang"), voice=False,
                        buttons=[(f"ord:{oid}:ready", "📦 Packed / ready"), (f"ord:{oid}:credit", "📒 Udhaar mein likho")])


async def _order_button(contact: dict, oid: int, action: str) -> None:
    _orders_table()
    o = db.q1("SELECT * FROM orders WHERE id=?", (oid,))
    if not o:
        await messenger.say(contact["phone"], "Ye order nahi mila.", _lang(contact), voice=False)
        return
    cust = C.get(o["contact_id"])
    if action in ("ok", "edit", "other"):
        if contact["phone"] != o["phone"] or o["status"] != "draft":
            await messenger.say(contact["phone"], "Ye order pehle hi update ho chuka hai.", _lang(contact), voice=False)
            return
        if action == "ok":
            await _order_confirmed(contact, oid)
        elif action == "edit":
            db.run("UPDATE orders SET status='changed' WHERE id=?", (oid,))
            await messenger.say(contact["phone"], "✏️ Theek hai. Poora order phir se boliye (voice note), main naya bana dunga.", _lang(contact))
        else:
            db.run("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
            await messenger.say(contact["phone"], "💬 Bataiye, aur kya madad karun? Baaki hisaab, payment, ya koi sawaal.", _lang(contact))
        return
    if contact["role"] not in ("owner", "staff"):
        return
    if action == "ready" and o["status"] in ("confirmed", "credited"):
        db.run("UPDATE orders SET status='ready' WHERE id=?", (oid,))
        await messenger.say(cust["phone"], f"📦 Aapka order #{oid} ready hai!", _lang(cust))
        await messenger.say(contact["phone"], f"👍 {cust['name']} ko bata diya: order #{oid} ready.", _lang(contact), voice=False)
    elif action == "credit" and o["status"] == "confirmed" and o["total"]:
        ledger.add(cust["id"], o["total"], "credit", note=f"order #{oid}", actor=contact["phone"])
        db.run("UPDATE orders SET status='credited' WHERE id=?", (oid,))
        await messenger.say(contact["phone"], f"📒 {cust['name']} +{_rs(o['total'])} udhaar likh diya (order #{oid}).", _lang(contact), voice=False)
        await messenger.say(cust["phone"], f"📒 Order #{oid}: {_rs(o['total'])} aapke khaate mein likha gaya. Baaki: {_rs(ledger.balance(cust['id']))}", _lang(cust))
    else:
        await messenger.say(contact["phone"], "Ye order pehle hi update ho chuka hai.", _lang(contact), voice=False)


# ------------------------------------------------------------------------------- owner/staff tools
async def t_query_balance(c, args, **kw):
    name = args.get("name") or ""
    if name:
        r = C.resolve(name)
        if r["status"] == "ok":
            cust = r["contact"]
            await messenger.say(c["phone"], f"{cust['name']}: baaki {_rs(ledger.balance(cust['id']))}", _lang(c))
            return
    rows = [b for b in ledger.balances() if b["balance"] > 0]
    total = sum(b["balance"] for b in rows)
    top = "\n".join(f"• {b['name']}: {_rs(b['balance'])}" + (f" ({b['age_days']} din)" if b["age_days"] else "") for b in rows[:6])
    await messenger.say(c["phone"], f"📒 Total baaki {_rs(total)} ({len(rows)} log)\n{top}", _lang(c))


async def t_ask_people(c, args, approval_reason=None, **kw):
    await _fanout(c, "poll", args.get("question") or kw.get("text", ""), args.get("people") or [], approval_reason)


async def t_send_task(c, args, approval_reason=None, **kw):
    await _fanout(c, "task", args.get("task") or kw.get("text", ""), args.get("people") or [], approval_reason)


async def _fanout(c: dict, kind: str, question: str, people: list[str], approval_reason: str | None) -> None:
    found, unknown = polls.resolve_people(people)
    if not found:
        await messenger.say(c["phone"], "Kis-kis ko bhejna hai? Naam ya 'delivery team / staff / partners' boliye. "
                            "(Contacts console mein add karein.)", _lang(c))
        return
    if approval_reason or len(found) > int(db.setting("fanout_approval") or 3):
        await _ask_owner_approval(c, {"type": "fanout", "kind": kind, "question": question, "people": [p["id"] for p in found]},
                                  f"{kind} to {len(found)} people: {question[:80]}")
        await messenger.say(c["phone"], f"⏳ {len(found)} logon ko bhejne se pehle owner approval maanga.", _lang(c), voice=False)
        return
    pid = await polls.create(kind, question, found, c["phone"])
    names = ", ".join(p["name"] for p in found)
    extra = f"\n(Nahi mile: {', '.join(unknown)})" if unknown else ""
    await messenger.say(c["phone"], f"📨 Bhej diya {len(found)} logon ko ({names}). Jawab aate hi bataunga.{extra}", _lang(c))
    db.audit(c["phone"], f"{kind}.created", {"poll": pid, "people": names})


async def t_set_reminder(c, args, **kw):
    when_text = str(args.get("when") or args.get("text") or "")
    date = parse_date(when_text) or dt.date.today().isoformat()
    m = re.search(r"(\d{1,2})\s*(baje|o'?clock|ganti|pm|am)", when_text.lower())
    hour = int(m.group(1)) if m else 9
    if m and m.group(2) == "pm" and hour < 12:
        hour += 12
    if m and m.group(2) in ("baje", "ganti") and hour < 8:
        hour += 12  # "5 baje" in a shop means 5 pm
    due = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(min(hour, 23), 0))
    if due.timestamp() < db.now():
        due = dt.datetime.fromtimestamp(db.now() + 3600)
    target = c
    if args.get("name"):
        r = C.resolve(args["name"], role=None)
        target = r["contact"] if r["status"] == "ok" else c
    db.run("INSERT INTO reminders(contact_id, text, due_at, created_at) VALUES (?,?,?,?)",
           (target["id"], f"⏰ {args.get('text') or when_text}", due.timestamp(), db.now()))
    await messenger.say(c["phone"], f"⏰ Yaad dila dunga: {due.strftime('%a %d %b, %I:%M %p')}", _lang(c))


async def t_send_document(c, args, approval_reason=None, **kw):
    kind = args.get("kind") or "bill"
    to = None
    if args.get("to"):
        r = C.resolve(args["to"], role=None)
        to = r["contact"] if r["status"] in ("ok",) else (r["candidates"][0]["contact"] if r["candidates"] else None)
    items = args.get("items") or []
    fields = {"to_name": (to or {}).get("name", args.get("to") or ""), "items": items, "note": args.get("note") or ""}
    if kind == "statement" and to:
        items = [{"name": f"{dt.datetime.fromtimestamp(e['created_at']).strftime('%d %b')} {'udhaar' if e['kind'] == 'credit' else 'jama'}",
                  "qty": 1, "rate": e["amount"] if e["kind"] == "credit" else -e["amount"]} for e in ledger.effective(to["id"])]
        fields["items"] = items
    doc = documents.make(kind, fields, (to or {}).get("id"))
    await _deliver_doc_with_approval(c, doc, to, f"{documents.DEFAULTS.get(kind, ('Doc',))[0]} for {fields['to_name'] or '—'}")


async def t_restock(c, args, approval_reason=None, **kw):
    supplier = (C.all_contacts("supplier") or [None])[0]
    items = [{"name": i.get("name", ""), "qty": i.get("qty", 1), "rate": 0} for i in (args.get("items") or [])]
    doc = documents.make("purchase_order", {"to_name": (supplier or {}).get("name", "Supplier"), "items": items,
                                            "note": "Please confirm dispatch / ETA"}, (supplier or {}).get("id"))
    await _deliver_doc_with_approval(c, doc, supplier, "Purchase order")


async def _deliver_doc_with_approval(c: dict, doc: dict, to: dict | None, title: str) -> None:
    owner_phone = _owner_phone()
    await messenger.send_file(owner_phone, doc["path"], doc["filename"], f"📄 Preview: {title}", doc["mime"])
    if not to or not to.get("phone"):
        await messenger.say(owner_phone, f"📄 {title} ready (recipient ka number nahi hai — khud forward karein).",
                            db.setting("owner_lang"), voice=False)
        return
    await _ask_owner_approval(c, {"type": "doc", "doc": doc, "to": to["id"], "title": title},
                              f"Send '{title}' to {to['name']}?")


async def t_daily_summary(c, args, **kw):
    await messenger.say(c["phone"], build_summary(), _lang(c))


def build_summary() -> str:
    t = ledger.today_totals()
    rows = [b for b in ledger.balances() if b["balance"] > 0]
    overdue = [b for b in rows if b["age_days"] > 30]
    promises = db.q("SELECT c.name, cl.date FROM claims cl JOIN contacts c ON c.id=cl.contact_id WHERE cl.kind='promise' AND cl.status='open'")
    disputes = db.q("SELECT id FROM claims WHERE kind='dispute' AND status='open'")
    open_polls = db.q("SELECT id FROM polls WHERE status='open'")
    lines = [f"🌙 Aaj ka hisaab — {db.setting('shop_name')}",
             f"{profiles.profile()['dues_word'].title()} diya {_rs(t['credit'])} · wapas aaya {_rs(t['payment'])}",
             f"Total baaki {_rs(sum(b['balance'] for b in rows))} ({len(rows)} log)"]
    if overdue:
        lines.append(f"30+ din: {', '.join(b['name'] for b in overdue[:5])}")
    if promises:
        lines.append("Vaade: " + ", ".join(f"{p['name']} ({_due_label(p['date']) or '?'})" for p in promises[:5]))
    if disputes:
        lines.append(f"Open disputes: {len(disputes)}")
    if open_polls:
        lines.append(f"Open sawaal/kaam: {len(open_polls)}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------- approvals
async def _ask_owner_approval(actor: dict, action: dict, summary: str) -> None:
    aid = db.run("INSERT INTO approvals(actor, summary, action, created_at) VALUES (?,?,?,?)",
                 (actor["phone"], summary, json.dumps(action, ensure_ascii=False), db.now()))
    await messenger.say(_owner_phone(), f"🔐 Approval: {summary}", db.setting("owner_lang"),
                        buttons=[(f"approve:{aid}", "📤 Haan, bhejo"), (f"reject:{aid}", "✖️ Cancel")], voice=False)


async def _approval(owner: dict, kind: str, aid: int) -> None:
    if owner["role"] != "owner":
        return
    ap = db.q1("SELECT * FROM approvals WHERE id=? AND status='open'", (aid,))
    if not ap:
        await messenger.say(owner["phone"], "Ye approval pehle hi ho chuka hai.", _lang(owner), voice=False)
        return
    db.run("UPDATE approvals SET status=? WHERE id=?", ("approved" if kind == "approve" else "rejected", aid))
    if kind == "reject":
        await messenger.say(owner["phone"], "✖️ Cancel kar diya.", _lang(owner), voice=False)
        await messenger.say(ap["actor"], f"✖️ Owner ne cancel kiya: {ap['summary'][:80]}", "hi-IN", voice=False)
        return
    await run_approved(owner, json.loads(ap["action"]), ap["actor"])


async def run_approved(owner: dict, action: dict, actor_phone: str) -> None:
    t = action.get("type")
    if t == "doc":
        to = C.get(action["to"])
        await messenger.send_file(to["phone"], action["doc"]["path"], action["doc"]["filename"],
                                  f"{db.setting('shop_name')}: {action['title']}", action["doc"]["mime"])
        await messenger.say(owner["phone"], f"📤 Bhej diya: {action['title']} → {to['name']}", _lang(owner), voice=False)
    elif t == "fanout":
        people = [C.get(i) for i in action["people"]]
        await polls.create(action["kind"], action["question"], [p for p in people if p], actor_phone)
        await messenger.say(owner["phone"], f"📨 Bhej diya {len(people)} logon ko.", _lang(owner), voice=False)
    elif t == "share":
        k = knowledge.get(action["kid"])
        people = [p for p in (C.get(i) for i in action["people"]) if p]
        for p in people:
            await messenger.send_file(p.get("phone") or "", k["path"], os.path.basename(k["path"]).split("_", 2)[-1],
                                      f"{db.setting('shop_name')}: {k['title']}", k["mime"] or "application/pdf")
        await messenger.say(owner["phone"], f"📤 '{k['title']}' bhej diya {len(people)} logon ko.", _lang(owner), voice=False)
    elif t == "announce":
        people = [p for p in (C.get(i) for i in action["people"]) if p]
        for p in people:
            await messenger.say(p.get("phone") or "", f"📢 {db.setting('shop_name')}: {action['message']}", _lang(p))
        await messenger.say(owner["phone"], f"📢 Announcement bhej diya {len(people)} logon ko.", _lang(owner), voice=False)
    elif t == "money":
        it = action["item"]
        it["issues"] = []
        actor = C.by_phone(actor_phone) or owner
        await _commit({**actor, "role": "owner"}, [it])


# ------------------------------------------------------------------------------- media (photos / PDFs)
async def on_media(contact: dict, mid: int, path: str, mime: str) -> None:
    if contact["role"] not in ("owner", "staff"):
        await messenger.say(contact["phone"], "📎 Mil gaya. Dukaan ko bhej diya.", _lang(contact), voice=False)
        await messenger.send_file(_owner_phone(), path, os.path.basename(path), f"📎 From {contact['name']}", mime)
        return
    await messenger.say(contact["phone"], "📎 Ye kya hai?", _lang(contact), voice=False,
                        buttons=[(f"media:{mid}:template", "🧾 Mera bill format"), (f"media:{mid}:supplier", "📥 Supplier bill"),
                                 (f"media:{mid}:ignore", "❌ Kuch nahi")])


async def _media_choice(contact: dict, mid: int, choice: str) -> None:
    msg = db.q1("SELECT * FROM messages WHERE id=?", (mid,))
    if not msg or choice == "ignore":
        return
    path, mime = msg["media"], json.loads(msg["meta"] or "{}").get("mime", "")
    with open(path, "rb") as f:
        data = f.read()
    await messenger.say(contact["phone"], "🔍 Padh raha hoon (Sarvam Vision)…", _lang(contact), voice=False)
    text = await docai.parse(data, os.path.basename(path), mime)
    if not text:
        await messenger.say(contact["phone"], "Document padh nahi paaya (SARVAM_API_KEY / file check karein). Console se template edit kar sakte hain.",
                            _lang(contact), voice=False)
        return
    if choice == "template":
        documents.save_custom("bill", text)
        await messenger.say(contact["phone"], "✅ Aapka format save ho gaya. Ab boliye: 'Sharma ji ko bill bhejo, 50 bag cement 380 ke rate se'.",
                            _lang(contact))
    else:
        _, nums = words_to_numbers(text)
        total = max(nums) if nums else 0
        await messenger.say(contact["phone"], f"📥 Supplier bill padh liya. Sabse bada amount {_rs(total)}.\n"
                            f"{text[:500]}", _lang(contact))


async def t_save_rule(c, args, **kw):
    """Teach the bot by voice (Prem's idea): 'Ab se 500 se upar udhaar mat dena bina mujhse puche'."""
    rule = (args.get("rule") or kw.get("text", "")).strip()
    did = db.run("INSERT INTO rule_drafts(owner_phone,text,created_at) VALUES (?,?,?)", (c["phone"], rule, db.now()))
    limit = knowledge.credit_limit(rule)
    effect = (f"Credit above {_rs(limit)} requires owner confirmation." if limit is not None
              else "Save these words as shop guidance for knowledge answers and the AI planner.")
    await messenger.say(c["phone"], f"Rule preview\n“{rule}”\n{effect}\nWhen should it apply?", _lang(c),
                        buttons=[(f"rule:{did}:today", "Today (IST)"), (f"rule:{did}:ongoing", "Ongoing"),
                                 (f"rule:{did}:cancel", "Cancel")])


async def t_share_document(c, args, approval_reason=None, **kw):
    """'Parents ko fee structure bhejo' -> find it in the knowledge base -> owner approval -> send."""
    hits = knowledge.find(args.get("title") or kw.get("text", ""), kind="file")
    if not hits or hits[0]["score"] < 55:
        await messenger.say(c["phone"], "Ye document knowledge base mein nahi mila. Console → Knowledge mein upload karein.", _lang(c))
        return
    doc = hits[0]
    people = args.get("people") or [f"@{doc['audience']}"]
    found, _ = polls.resolve_people(people)
    if not found:
        await messenger.say(c["phone"], f"'{doc['title']}' kisko bhejna hai? Naam ya group boliye.", _lang(c))
        return
    await _ask_owner_approval(c, {"type": "share", "kid": doc["id"], "people": [p["id"] for p in found]},
                              f"Share '{doc['title']}' with {len(found)} ({', '.join(p['name'] for p in found[:4])}{'…' if len(found) > 4 else ''})")
    if c["role"] != "owner":
        await messenger.say(c["phone"], "⏳ Owner approval ke liye bheja.", _lang(c), voice=False)


async def t_announce(c, args, approval_reason=None, **kw):
    """One-way announcement to people or groups, each in their own language (no buttons)."""
    found, _ = polls.resolve_people(args.get("people") or [])
    msg = args.get("message") or kw.get("text", "")
    if not found:
        await messenger.say(c["phone"], "Kisko announce karna hai? Naam ya group boliye.", _lang(c))
        return
    await _ask_owner_approval(c, {"type": "announce", "message": msg, "people": [p["id"] for p in found]},
                              f"Announce to {len(found)}: {msg[:80]}")


async def t_mark_attendance(c, args, **kw):
    date = parse_date(str(args.get("date") or "")) or dt.date.today().isoformat()
    status = (args.get("status") or "present").lower()
    status = "absent" if any(w in status for w in ("absent", "nahi", "illa", "chutti", "leave")) else "present"
    found, unknown = polls.resolve_people(args.get("people") or [])
    for p in found:
        db.run("INSERT INTO attendance(contact_id, date, status, by, created_at) VALUES (?,?,?,?,?) "
               "ON CONFLICT(contact_id, date) DO UPDATE SET status=excluded.status, by=excluded.by",
               (p["id"], date, status, c["phone"], db.now()))
    names = ", ".join(p["name"] for p in found) or "—"
    extra = f" (nahi mile: {', '.join(unknown)})" if unknown else ""
    await messenger.say(c["phone"], f"🗓️ {_due_label(date)}: {names} → {status}{extra}", _lang(c))


def _price_list() -> str:
    rows = db.q("SELECT name, unit, price FROM catalog WHERE price > 0 ORDER BY name")
    lines = [f"- {r['name']}: Rs {r['price']:g} per {r['unit'] or 'unit'}" for r in rows]
    return "TODAY'S PRICE LIST (set by the shop):\n" + "\n".join(lines) if rows else ""


async def t_update_price(c, args, **kw):
    """The owner says a new price by voice; the catalog (the bot's only price source) changes for every customer."""
    from rapidfuzz import fuzz, process
    done = []
    for it in args.get("items") or []:
        name = str((it or {}).get("name") or "").strip()
        try:
            price = float((it or {}).get("price"))
        except (TypeError, ValueError):
            continue
        if not name or price <= 0:
            continue
        cat = db.q("SELECT * FROM catalog")
        keys = {k.lower(): r for r in cat for k in [r["name"], *json.loads(r["aliases"] or "[]")]}
        hit = process.extractOne(name.lower(), list(keys), scorer=fuzz.WRatio) if keys else None
        if hit and hit[1] >= 80:
            row = keys[hit[0]]
            db.run("UPDATE catalog SET price=? WHERE id=?", (price, row["id"]))
            done.append(f"{row['name']}: {_rs(price)}/{row['unit'] or 'unit'} (pehle {_rs(row['price'])})")
        else:
            unit = str((it or {}).get("unit") or "")
            db.run("INSERT INTO catalog(name, aliases, unit, price) VALUES (?,?,?,?)", (name.title(), "[]", unit, price))
            done.append(f"{name.title()}: {_rs(price)} (naya item)")
    if not done:
        await messenger.say(c["phone"], "Kaunsa item, kitne ka? Jaise boliye: 'tomato ka rate 40 kar do'.", _lang(c))
        return
    db.audit(c["phone"], "price_update", done)
    said = (kw.get("text") or "").lower()
    if args.get("notify") or re.search(r"sab(ko|ke)|sabhi|everyone|all customers|notify|bata do|batao|bhej do", said):
        # Every customer hears it in their own language (Kannada, Hindi, Tamil, English...).
        shop = db.setting("shop_name") or "Shop"
        people = [x for x in C.all_contacts() if x["role"] == "customer" and x["phone"]]
        lines = "\n".join("• " + d.split(" (pehle")[0] for d in done)
        await asyncio.gather(*(messenger.say(p["phone"], f"📢 {shop}: price update\n{lines}", _lang(p)) for p in people))
        done.append(f"{len(people)} customers ko bata diya")
    await messenger.say(c["phone"], "✅ Price list update:\n" + "\n".join("• " + d for d in done) +
                        "\nAb customers ko yahi rate bataunga.", _lang(c))


async def t_save_fact(c, args, **kw):
    text = (args.get("text") or kw.get("text", "")).strip()
    if not text:
        return
    knowledge.add_fact(text[:40], text, "customer")
    await messenger.say(c["phone"], f"📌 Yaad rakh liya, customers poochenge to bataunga:\n“{text[:200]}”", _lang(c))


async def t_answer_question(c, args, **kw):
    """Answer from the owner's knowledge base and today's price list; if unsure, pass the question to the owner."""
    q = args.get("question") or kw.get("text", "")
    ctx = "\n".join(x for x in (_price_list(), knowledge.context_for_llm()) if x)
    answer = ""
    if ctx:
        from brain import llm
        out, _ = llm.json_call("You answer customer questions for a small Indian business using ONLY the facts given. "
                               "If the facts don't answer it, return an empty answer. Reply in the customer's language. "
                               'Return JSON {"answer": "..."}', f"FACTS:\n{ctx}\n\nQUESTION: {q}")
        answer = (out or {}).get("answer", "")
        if not answer:
            hits = knowledge.find(q, kind="fact")
            if hits and hits[0]["score"] >= 70:
                answer = hits[0]["text"]
    if answer:
        await messenger.say(c["phone"], answer, _lang(c))
        return
    await messenger.say(c["phone"], "🙏 Aapka sawaal dukaan tak pahucha diya, jawab jaldi aayega.", _lang(c))
    await messenger.say(_owner_phone(), f"❓ {c['name']} pooch rahe hain: {q[:200]}\n(Live tab se jawab dein)", db.setting("owner_lang"), voice=False)


TOOLS = {
    "save_rule": t_save_rule, "share_document": t_share_document, "announce": t_announce, "mark_attendance": t_mark_attendance,
    "answer_question": t_answer_question, "request_bill": t_request_bill, "update_price": t_update_price, "save_fact": t_save_fact,
    "query_balance": t_query_balance, "ask_people": t_ask_people, "send_task": t_send_task,
    "set_reminder": t_set_reminder, "send_document": t_send_document, "restock": t_restock,
    "correct_last": t_correct_last, "undo_last": t_undo_last, "daily_summary": t_daily_summary,
    "query_own_balance": t_query_own_balance, "promise": t_promise, "dispute": t_dispute,
    "paid_claim": t_paid_claim, "create_order": t_create_order,
}


# ------------------------------------------------------------------------------- scheduler
async def tick() -> None:
    for r in db.q("SELECT * FROM reminders WHERE status='open' AND due_at <= ?", (db.now(),)):
        c = C.get(r["contact_id"])
        if c:
            await messenger.say(c["phone"] or "", r["text"], _lang(c))
        db.run("UPDATE reminders SET status='sent' WHERE id=?", (r["id"],))
    await polls.follow_up()
    hhmm = dt.datetime.now().strftime("%H:%M")
    today = dt.date.today().isoformat()
    if hhmm >= (db.setting("summary_time") or "21:00") and db.setting("summary_last") != today and _owner_phone():
        db.set_setting("summary_last", today)
        await messenger.say(_owner_phone(), build_summary(), db.setting("owner_lang"))
