"""Bolo backend: WhatsApp webhook, owner console API, simulator, scheduler.

Run (from backend/):  uvicorn app:app --port 8000
Open:                 http://localhost:8000  (owner console + phone simulator)
"""
import asyncio
import base64
import html
import io
import json
import os
from urllib.parse import urlencode

import config  # loads .env first
import db
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from brain import agent
from core import contacts as C
from core import ledger
from features import documents, knowledge, polls, profiles
from pipe import inbox, webhooks

app = FastAPI(title="Bolo", version="0.1")
CONSOLE_DIR = os.path.join(config.ROOT, "frontend")


@app.on_event("startup")
async def _startup() -> None:
    db.init()
    knowledge.init()
    documents.seed_templates()

    async def loop():
        while True:
            try:
                await inbox.resume()
                await agent.tick()
            except Exception as e:
                print("[scheduler]", e)
            await asyncio.sleep(30)

    asyncio.create_task(loop())


app.include_router(webhooks.router)


# ---------------------------------------------------------------- simulator (no WhatsApp needed)
@app.post("/api/simulate")
async def simulate(payload: dict):
    phone = payload.get("phone", "")
    if not isinstance(phone, str) or not C.normalize_phone(phone):
        raise HTTPException(400, "A phone number is required.")
    button, text = payload.get("button", ""), payload.get("text", "")
    if not isinstance(button, str) or not isinstance(text, str) or not (button or text.strip()):
        raise HTTPException(400, "Enter a message or choose a reply button.")
    name = payload.get("name", "") if isinstance(payload.get("name", ""), str) else ""
    if button:
        await agent.handle(phone, "button", button=button, profile_name=name[:40])
    else:
        await agent.handle(phone, "text", text=text, profile_name=name[:40])
    return {"ok": True}


@app.post("/api/simulate/audio")
async def simulate_audio(phone: str = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    ext = (os.path.splitext(file.filename or "")[1] or ".webm").lstrip(".")
    review = await agent.handle(phone, "audio", audio_bytes=data, audio_ext=ext, review_local=True)
    return {"ok": True, "review": review}


@app.post("/api/simulate/review")
async def review_audio(payload: dict):
    phone = payload.get("phone", "")
    message_id = payload.get("message_id")
    text = payload.get("text", "")
    discard = payload.get("discard", False)
    if not isinstance(phone, str) or type(message_id) is not int or type(discard) is not bool:
        raise HTTPException(400, "Choose a recording and speaker.")
    if not isinstance(text, str) or (not discard and not 0 < len(text.strip()) <= 8000):
        raise HTTPException(400, "Enter a transcript of up to 8,000 characters.")
    try:
        status = await agent.review_voice(C.normalize_phone(phone), message_id, text.strip(), discard)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return {"ok": True, "status": status}


@app.post("/api/simulate/media")
async def simulate_media(phone: str = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    await agent.handle(phone, "media", media=data, mime=file.content_type or "", filename=file.filename or "upload")
    return {"ok": True}


@app.get("/api/messages")
async def messages(phone: str = "", after: int = 0):
    if phone:
        rows = db.q("SELECT * FROM messages WHERE phone=? AND id>? ORDER BY id", (C.normalize_phone(phone), after))
    else:
        rows = db.q("SELECT * FROM messages WHERE id>? ORDER BY id DESC LIMIT 200", (after,))
    for r in rows:
        r["buttons"] = json.loads(r["buttons"] or "[]")
        r["meta"] = json.loads(r["meta"] or "{}")
    return rows


# ---------------------------------------------------------------- console API
@app.get("/api/status")
async def status():
    return {"config": config.status(), "owner": C.owner(), "verify": ledger.verify_chain()}


@app.get("/api/settings")
async def get_settings():
    return {r["key"]: r["value"] for r in db.q("SELECT * FROM settings")}


@app.put("/api/settings")
async def put_settings(payload: dict):
    for k, v in payload.items():
        db.set_setting(k, v)
        if k == "owner_phone" and v:
            o = C.owner()
            if o:
                C.upsert(o["name"], v, "owner", o["lang"], o["aliases"], o["credit_limit"], 1, o["note"], cid=o["id"])
            else:
                C.upsert("Owner", v, role="owner", lang=db.setting("owner_lang"), opted_in=1)
    return await get_settings()


@app.get("/api/contacts")
async def list_contacts():
    bals = {b["id"]: b for b in ledger.balances()}
    out = []
    for c in C.all_contacts():
        b = bals.get(c["id"], {})
        out.append({**c, "balance": b.get("balance", 0), "age_days": b.get("age_days", 0)})
    return out


@app.post("/api/contacts")
async def save_contact(p: dict):
    aliases = p.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [a.strip() for a in aliases.split(",") if a.strip()]
    c = C.upsert(p["name"], p.get("phone", ""), p.get("role", "customer"), p.get("lang", "hi-IN"), aliases,
                 float(p.get("credit_limit") or 0), int(p.get("opted_in") or 0), p.get("note", ""), cid=p.get("id"))
    if p.get("reply_mode") in ("both", "voice", "text"):
        db.run("UPDATE contacts SET reply_mode=? WHERE id=?", (p["reply_mode"], c["id"]))
    return C.get(c["id"])


@app.delete("/api/contacts/{cid}")
async def delete_contact(cid: int):
    if db.q1("SELECT id FROM ledger WHERE contact_id=?", (cid,)):
        raise HTTPException(400, "Contact has ledger entries; it can't be deleted (audit).")
    db.run("DELETE FROM contacts WHERE id=?", (cid,))
    return {"ok": True}


@app.get("/api/catalog")
async def list_catalog():
    return db.q("SELECT * FROM catalog ORDER BY name")


@app.post("/api/catalog")
async def save_item(p: dict):
    aliases = json.dumps([a.strip() for a in str(p.get("aliases", "")).split(",") if a.strip()], ensure_ascii=False)
    if p.get("id"):
        db.run("UPDATE catalog SET name=?, aliases=?, unit=?, price=? WHERE id=?",
               (p["name"], aliases, p.get("unit", ""), float(p.get("price") or 0), p["id"]))
        return {"id": p["id"]}
    return {"id": db.run("INSERT INTO catalog(name, aliases, unit, price) VALUES (?,?,?,?)",
                         (p["name"], aliases, p.get("unit", ""), float(p.get("price") or 0)))}


@app.delete("/api/catalog/{iid}")
async def delete_item(iid: int):
    db.run("DELETE FROM catalog WHERE id=?", (iid,))
    return {"ok": True}


@app.get("/api/ledger")
async def get_ledger(contact_id: int | None = None):
    rows = db.q("SELECT l.*, c.name FROM ledger_current l JOIN contacts c ON c.id=l.contact_id"
                + (" WHERE l.contact_id=?" if contact_id else "") + " ORDER BY l.id DESC LIMIT 300",
                (contact_id,) if contact_id else ())
    rev = ledger.reversed_ids()
    for r in rows:
        r["reversed"] = r["id"] in rev
        ev = db.q1("SELECT transcript, transcript_b FROM events WHERE id=?", (r["event_id"],)) if r["event_id"] else None
        r["transcript"] = (ev or {}).get("transcript", "")
        audio = [f for f in os.listdir(config.AUDIO_DIR) if r["audio_sha"] and f.startswith(r["audio_sha"][:16])]
        r["audio"] = f"/audio/{audio[0]}" if audio else ""
    return {"entries": rows, "balances": ledger.balances(), "today": ledger.today_totals(), "verify": ledger.verify_chain()}


@app.get("/api/claims")
async def get_claims():
    return db.q("SELECT cl.*, c.name FROM claims cl JOIN contacts c ON c.id=cl.contact_id ORDER BY cl.id DESC LIMIT 100")


@app.get("/api/polls")
async def get_polls():
    return [polls.tally(p["id"]) for p in db.q("SELECT id FROM polls ORDER BY id DESC LIMIT 50")]


@app.get("/api/approvals")
async def get_approvals():
    return db.q("SELECT * FROM approvals ORDER BY id DESC LIMIT 50")


@app.post("/api/approvals/{aid}/{decision}")
async def decide(aid: int, decision: str):
    owner = C.owner()
    if not owner:
        raise HTTPException(400, "Set the owner phone in Settings first")
    await agent.on_button(owner, f"{'approve' if decision == 'approve' else 'reject'}:{aid}")
    return {"ok": True}


@app.get("/api/templates")
async def get_templates():
    return db.q("SELECT * FROM templates ORDER BY name")


@app.put("/api/templates/{name}")
async def put_template(name: str, p: dict):
    db.run("UPDATE templates SET html=? WHERE name=?", (p["html"], name))
    return {"ok": True}


@app.get("/api/templates/{name}/preview", response_class=HTMLResponse)
async def preview_template(name: str):
    return documents.render(name, {"to_name": "Sharma ji", "items": [{"name": "Cement bag", "qty": 50, "rate": 380}],
                                   "note": "Sample preview"})


@app.get("/api/summary")
async def summary():
    return {"text": agent.build_summary()}


@app.post("/api/summary/send")
async def send_summary():
    from pipe import messenger
    owner = C.owner()
    if owner:
        await messenger.say(owner["phone"], agent.build_summary(), owner["lang"])
    return {"ok": bool(owner)}


@app.get("/api/audit")
async def audit():
    return db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 200")


@app.post("/api/seed")
async def seed(kind: str = "kirana"):
    """Demo data for a kirana (default) or a school."""
    from seed import run as seed_run
    return seed_run(kind)


# ---------------------------------------------------------------- onboarding, profile, features
@app.get("/api/profile")
async def get_profile():
    return {**profiles.profile(), "types": {k: v["label"] for k, v in profiles.PROFILES.items()},
            "all_features": {k: {"label": v[0], "desc": v[1], "core": v[2]} for k, v in profiles.FEATURES.items()}}


@app.post("/api/onboard")
async def onboard(p: dict):
    prof = profiles.apply(p.get("description", ""), p.get("name") or None, p.get("type") or None)
    if p.get("owner_lang"):
        db.set_setting("owner_lang", p["owner_lang"])
    if p.get("owner_phone"):
        await put_settings({"owner_phone": p["owner_phone"]})
    return prof


@app.put("/api/features/{key}")
async def set_feature(key: str, p: dict):
    if key not in profiles.FEATURES:
        raise HTTPException(404)
    return {"features": profiles.toggle(key, bool(p.get("on")))}


@app.post("/api/reset")
async def reset():
    """Archive the current shop and restart onboarding."""
    archive = db.reset()
    knowledge.init()
    documents.seed_templates()
    return {"ok": True, "archive": archive}


# ---------------------------------------------------------------- knowledge base
@app.get("/api/knowledge")
async def list_knowledge():
    return knowledge.all_items()


@app.post("/api/knowledge/file")
async def add_knowledge_file(title: str = Form(...), audience: str = Form("customer"), file: UploadFile = File(...)):
    data = await file.read()
    from voice import docai
    text = await docai.parse(data, file.filename or "file", file.content_type or "")
    return knowledge.add_file(title, data, file.filename or "file", file.content_type or "", audience, text)


@app.post("/api/knowledge/fact")
async def add_knowledge_fact(p: dict):
    return knowledge.add_fact(p["title"], p["text"], p.get("audience", "customer"))


@app.delete("/api/knowledge/{kid}")
async def delete_knowledge(kid: int):
    knowledge.delete(kid)
    return {"ok": True}


@app.post("/api/knowledge/{kid}/send")
async def send_knowledge(kid: int, p: dict):
    """Owner shares a file from the console with a role group (the owner acting = approved)."""
    owner = C.owner()
    k = knowledge.get(kid)
    if not owner or not k:
        raise HTTPException(400, "Owner or file missing")
    people = [c["id"] for c in C.all_contacts(p["role"])] if p.get("role") else p.get("people", [])
    await agent.run_approved(owner, {"type": "share", "kid": kid, "people": people}, owner["phone"])
    return {"sent": len(people)}


# ---------------------------------------------------------------- live watch & takeover
@app.get("/api/live/threads")
async def live_threads():
    from features.watch import summarize

    rows = db.q("""SELECT m.*, recent.n, incoming.text AS inbound_text, incoming.kind AS inbound_kind,
               incoming.meta AS inbound_metadata
        FROM (SELECT phone, MAX(id) AS last_id, COUNT(*) AS n,
                     MAX(CASE WHEN direction='in' THEN id END) AS inbound_id
              FROM messages GROUP BY phone) AS recent
        JOIN messages m ON m.id=recent.last_id
        LEFT JOIN messages incoming ON incoming.id=recent.inbound_id
        ORDER BY m.id DESC LIMIT 100""")
    out = []
    for r in rows:
        c = C.by_phone(r["phone"]) or {}
        out.append({"phone": r["phone"], "name": c.get("name", r["phone"]), "role": c.get("role", ""),
                    "role_label": profiles.role_label(c.get("role") or "customer"), "paused": bool(c.get("paused")),
                    "last": (r["text"] or "")[:90], "kind": r["kind"], "direction": r["direction"], "at": r["created_at"],
                    "count": r["n"], **summarize(r["inbound_text"], r["inbound_kind"], json.loads(r["inbound_metadata"] or "{}"))})
    return {"mode": db.setting("bot_mode"), "whatsapp": config.status()["whatsapp"], "threads": out}


@app.post("/api/live/mode")
async def live_mode(p: dict):
    db.set_setting("bot_mode", "paused" if p.get("paused") else "auto")
    db.audit("owner", "bot_mode", db.setting("bot_mode"))
    return {"mode": db.setting("bot_mode")}


@app.post("/api/live/takeover")
async def takeover(p: dict):
    c = C.by_phone(p["phone"])
    if not c:
        raise HTTPException(404)
    db.run("UPDATE contacts SET paused=? WHERE id=?", (1 if p.get("paused") else 0, c["id"]))
    db.audit("owner", "takeover" if p.get("paused") else "handback", {"phone": c["phone"]})
    return {"paused": bool(p.get("paused"))}


@app.post("/api/live/reply")
async def human_reply(p: dict):
    from pipe import messenger
    c = C.by_phone(p["phone"])
    await messenger.say(C.normalize_phone(p["phone"]), p["text"], (c or {}).get("lang", "hi-IN"), voice=False,
                        meta={"human": True})
    return {"ok": True}


@app.get("/api/attendance")
async def attendance(date: str = ""):
    import datetime as _dt
    date = date or _dt.date.today().isoformat()
    return db.q("SELECT a.*, c.name FROM attendance a JOIN contacts c ON c.id=a.contact_id WHERE a.date=? ORDER BY c.name", (date,))


# ---------------------------------------------------------------- files, payments, console
@app.get("/audio/{name}")
async def get_audio(name: str):
    path = os.path.join(config.AUDIO_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/files/{name}")
async def get_file(name: str):
    path = os.path.join(config.DOCS_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/pay/{contact_id}", response_class=HTMLResponse)
async def pay_page(contact_id: int, amount: float = 0):
    c = C.get(contact_id)
    upi = db.setting("upi_id")
    if not c or not upi:
        raise HTTPException(404)
    amount = amount or ledger.balance(contact_id)
    shop = db.setting("shop_name")
    fields = {"pa": upi, "pn": shop, "am": f"{amount:.2f}", "cu": "INR", "tn": f"Bolo {c['name']}"}
    link = f"upi://pay?{urlencode(fields)}"
    qr_img = ""
    try:
        import qrcode
        buf = io.BytesIO()
        qrcode.make(link).save(buf, format="PNG")
        qr_img = f"<img src='data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}' width=240>"
    except Exception:
        pass
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>Pay {html.escape(shop)}</title>
<body style="font-family:system-ui;text-align:center;padding:24px"><h2>{html.escape(shop)}</h2><p>{html.escape(c['name'])}</p>
<h1>₹{amount:,.2f}</h1>{qr_img}<p><a href="{html.escape(link)}" style="display:inline-block;padding:14px 22px;background:#0a7;color:#fff;
border-radius:10px;text-decoration:none">Pay with any UPI app</a></p><p style="color:#777">After paying, reply "paid" on WhatsApp.</p></body>"""


@app.get("/health")
async def health():
    return {"ok": True}


# One server, three doors (same agent, same database):
#   SITE_PORT (8000)     product landing page, owner dashboard (/console/) and the API
#   CUSTOMER_PORT (8001) customer side: full-screen WhatsApp-style chat (/chat/)
#   BUSINESS_PORT (8002) business side: login, live chat logs of every customer, the assistant (/business)
SITE_DIR = os.path.join(config.ROOT, "product-demo")
CHAT_DIR = os.path.join(config.ROOT, "chat")


@app.get("/")
async def root(request: Request):
    port = (request.scope.get("server") or ("", 0))[1]
    if port == config.CUSTOMER_PORT:
        return RedirectResponse("/chat/")
    if port == config.BUSINESS_PORT:
        return RedirectResponse("/business")
    return RedirectResponse("/site/" if os.path.isdir(SITE_DIR) else "/console/")


@app.get("/business")
async def business_portal():
    return FileResponse(os.path.join(CHAT_DIR, "index.html"))


if os.path.isdir(CONSOLE_DIR):
    app.mount("/console", StaticFiles(directory=CONSOLE_DIR, html=True), name="console")
    # Bolo Chat: a separate WhatsApp-style app for customers/staff on their own phone (open via the tunnel URL).
    app.mount("/chat", StaticFiles(directory=CHAT_DIR, html=True), name="chat")
if os.path.isdir(SITE_DIR):
    app.mount("/site", StaticFiles(directory=SITE_DIR, html=True), name="site")
