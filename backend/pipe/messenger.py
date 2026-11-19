"""One place to talk to people. Every outgoing message is stored (the console shows it and it's
the audit trail). If WhatsApp credentials exist it is also sent for real; otherwise the web
simulator is the phone. Text is translated into the recipient's language and, when voice
replies are on, also spoken as a native WhatsApp voice note."""
import json
import os
import uuid
import httpx

import config
import db
from pipe import whatsapp as wa
from pipe import shares, twilio
from voice import translate, tts


def _store(phone: str, kind: str, text: str = "", buttons=None, media: str = "", meta=None) -> int:
    return db.run("INSERT INTO messages(direction, phone, kind, text, buttons, media, meta, created_at)"
                  " VALUES ('out',?,?,?,?,?,?,?)",
                  (phone, kind, text, json.dumps(buttons or [], ensure_ascii=False), media,
                   json.dumps(meta or {}, ensure_ascii=False), db.now()))


def store_inbound(phone: str, kind: str, text: str = "", media: str = "", meta=None) -> int:
    return db.run("INSERT INTO messages(direction, phone, kind, text, buttons, media, meta, created_at)"
                  " VALUES ('in',?,?,?,'[]',?,?,?)",
                  (phone, kind, text, media, json.dumps(meta or {}, ensure_ascii=False), db.now()))


async def _localize(text: str, lang: str) -> str:
    if not lang or lang == "hi-IN":
        return text  # our base copy is Hinglish; Hindi speakers read it fine (English speakers get a translation)
    out = await translate.to_lang(text, lang)
    # Safety: machine translation once invented "Date: 21/11/2023" on a money card. If the
    # translation adds or drops any number (amount, date, phone), send the original instead.
    # Same for currency: a translator once turned "₹20" into "$20".
    if any(sym in out and sym not in text for sym in ("$", "€", "£", "USD")):
        return text
    return out if _numbers(out) == _numbers(text) else text


def _numbers(s: str) -> set[str]:
    import re, unicodedata
    return {"".join(str(unicodedata.digit(ch)) for ch in m) for m in re.findall(r"\d+", s or "")}


async def _deliver(mid, phone, send, *args):
    """Only an actual inbound provider message opens a 24-hour service window."""
    provider = "meta" if config.WHATSAPP_LIVE else "twilio"
    meta = json.loads(db.q1("SELECT meta FROM messages WHERE id=?", (mid,))["meta"])
    meta["provider"] = provider
    recent = db.q1("SELECT 1 FROM webhook_inbox WHERE provider=? AND phone=? AND state!='retired' AND received_at>? LIMIT 1",
                   (provider, phone, db.now() - 86400))
    if not recent:
        meta["delivery"] = "outside_service_window"
    else:
        try:
            await send(phone, *args)
            meta["delivery"] = "accepted"
        except Exception as exc:
            meta["delivery"] = "failed"
            meta["error"] = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                meta["http_status"] = exc.response.status_code
    db.run("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), mid))
    if meta["delivery"] != "accepted":
        db.audit(provider, "message_delivery", {"message": mid, "state": meta["delivery"], "error": meta.get("error")})


def _numbered(text: str, buttons) -> str:
    return text + "\n\n" + "\n".join(f"{i + 1}. {t}" for i, (_, t) in enumerate(buttons)) + "\n(Reply with the number)"


def _reply_mode(phone: str) -> str:
    r = db.q1("SELECT reply_mode FROM contacts WHERE phone=?", (phone,))
    return (r or {}).get("reply_mode") or "both"


async def say(phone: str, text: str, lang: str = "hi-IN", buttons: list[tuple[str, str]] | None = None,
              voice: bool | None = None, meta: dict | None = None) -> None:
    """Send text (+ optional buttons) and, if enabled, the same text as a voice note."""
    if not phone:
        return
    local = await _localize(text, lang)
    shown = local if local == text else f"{local}\n\n({text})"
    mid = _store(phone, "buttons" if buttons else "text", shown, [list(b) for b in (buttons or [])], meta=meta)
    if config.WHATSAPP_LIVE:
        if buttons:
            await _deliver(mid, phone, wa.send_buttons, shown, buttons)
        else:
            await _deliver(mid, phone, wa.send_text, shown)
    elif config.TWILIO_LIVE:
        await _deliver(mid, phone, twilio.send, _numbered(shown, buttons) if buttons else shown)
    if voice is None:
        voice = db.setting("voice_replies") == "1"
    mode = _reply_mode(phone)  # Voice Passport: deaf users -> text only; low-literacy users -> always voice
    if mode == "text":
        voice = False
    elif mode == "voice" and voice is not False:
        voice = True
    if voice and tts.available():
        try:
            spoken = _speakable(local)
            ogg = await tts.speak(spoken, lang)
            name = f"out_{uuid.uuid4().hex[:12]}.ogg"
            with open(os.path.join(config.AUDIO_DIR, name), "wb") as f:
                f.write(ogg)
            mid = _store(phone, "voice", spoken, media=f"/audio/{name}")
            if config.WHATSAPP_LIVE:
                await _deliver(mid, phone, wa.send_voice, ogg)
            elif config.TWILIO_LIVE:
                await _deliver(mid, phone, twilio.send, "🔊", shares.make("audio", name))
        except Exception as exc:
            db.audit("speech", "voice_reply_failed", {"message": mid, "error": type(exc).__name__})


def _speakable(text: str) -> str:
    # Voice notes should not read out emoji, separators or button hints.
    import re
    t = re.sub(r"[①-⓿☀-➿\U0001F300-\U0001FAFF]", "", text)
    return re.sub(r"\s+", " ", t.replace("·", ",").replace("₹", "rupees ")).strip()[:600]


async def send_file(phone: str, path: str, filename: str, caption: str = "", mime: str = "application/pdf") -> None:
    url = f"/files/{os.path.basename(path)}"
    mid = _store(phone, "document", caption, media=url, meta={"filename": filename})
    if config.WHATSAPP_LIVE:
        if mime == "application/pdf":
            with open(path, "rb") as f:
                data = f.read()
            await _deliver(mid, phone, wa.send_document, data, filename, caption)
        else:
            link = shares.make("file", os.path.basename(path))
            await _deliver(mid, phone, wa.send_text, f"{caption}\n{link}")
    elif config.TWILIO_LIVE:
        await _deliver(mid, phone, twilio.send, caption or filename, shares.make("file", os.path.basename(path)))


def payment_url(contact_id: int, amount: float) -> str:
    if config.WHATSAPP_LIVE or config.TWILIO_LIVE:
        return shares.make("pay", {"contact_id": contact_id, "amount": amount})
    return f"{config.PUBLIC_BASE_URL}/pay/{contact_id}?amount={amount:g}"


async def send_link(phone: str, text: str, url: str) -> None:
    body = f"{text}\n{url}"
    mid = _store(phone, "text", body)
    if config.WHATSAPP_LIVE:
        await _deliver(mid, phone, wa.send_text, body)
    elif config.TWILIO_LIVE:
        await _deliver(mid, phone, twilio.send, body)
