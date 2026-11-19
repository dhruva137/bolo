"""Validate provider callbacks, queue the supported events, and acknowledge promptly."""
import asyncio
import json
import re

from fastapi import APIRouter, BackgroundTasks, Request, Response

import config
from pipe import inbox, twilio, whatsapp

router = APIRouter()


def objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def string(obj, key):
    value = obj.get(key)
    return value if isinstance(value, str) else ""


def meta_events(body):
    for entry in objects(body.get("entry")):
        for change in objects(entry.get("changes")):
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict) or string(metadata, "phone_number_id") != config.WA_PHONE_NUMBER_ID:
                continue
            names = {}
            for contact in objects(value.get("contacts")):
                profile = contact.get("profile")
                if isinstance(profile, dict):
                    names[string(contact, "wa_id")] = string(profile, "name")
            for msg in objects(value.get("messages")):
                msg_id, phone, kind = string(msg, "id"), string(msg, "from"), string(msg, "type")
                part = msg.get(kind)
                if not msg_id or not re.fullmatch(r"[0-9]{5,15}", phone) or not isinstance(part, dict):
                    continue
                event = {"phone": phone, "kind": kind, "profile_name": names.get(phone, "")}
                if kind == "text" and string(part, "body"):
                    event["text"] = part["body"]
                elif kind == "interactive":
                    reply = part.get("button_reply") or part.get("list_reply")
                    if not isinstance(reply, dict) or not string(reply, "id"):
                        continue
                    event.update(kind="button", button=reply["id"])
                elif kind in ("audio", "image", "document") and string(part, "id").isascii() and string(part, "id").isdigit():
                    event.update(resource=part["id"], mime=string(part, "mime_type"))
                    if kind != "audio":
                        event.update(text=string(part, "caption"), filename=string(part, "filename") or kind)
                else:
                    continue
                yield msg_id, event


@router.get("/webhook")
async def verify(request: Request):
    query = request.query_params
    if query.get("hub.mode") == "subscribe" and query.get("hub.verify_token") == whatsapp.VERIFY_TOKEN:
        return Response(query.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook")
async def receive(request: Request, bg: BackgroundTasks):
    if not config.WHATSAPP_LIVE or not whatsapp.APP_SECRET:
        return Response(status_code=503)
    raw = await request.body()
    if not whatsapp.signature_ok(raw, request.headers.get("X-Hub-Signature-256", "")):
        return Response(status_code=401)
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        return Response(status_code=400)
    if not isinstance(body, dict):
        return Response(status_code=400)
    for msg_id, event in meta_events(body):
        if inbox.enqueue("meta", msg_id, event):
            bg.add_task(inbox.process, "meta", msg_id)
    return {"ok": True}


def twilio_event(form):
    if form.get("AccountSid") != config.TWILIO_SID or form.get("To") != config.TWILIO_FROM:
        return None
    sender = re.fullmatch(r"whatsapp:\+([0-9]{5,15})", form.get("From", ""))
    msg_id = form.get("MessageSid", "")
    if not sender or not msg_id:
        return None
    event = {"phone": sender.group(1), "kind": "text", "profile_name": form.get("ProfileName", "")}
    count = form.get("NumMedia", "0")
    if count == "0" and form.get("Body"):
        event["text"] = form["Body"]
    elif count == "1" and twilio.valid_media_url(form.get("MediaUrl0", "")):
        mime = form.get("MediaContentType0", "")
        event.update(kind="audio" if mime.startswith("audio/") else "media", mime=mime, resource=form["MediaUrl0"])
        if event["kind"] == "media":
            event.update(text=form.get("Body", ""), filename="upload")
    else:
        return None
    return msg_id, event


@router.post("/twilio")
async def twilio_in(request: Request, bg: BackgroundTasks):
    if not config.TWILIO_LIVE:
        return Response(status_code=503)
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/x-www-form-urlencoded":
        return Response(status_code=415)
    form = await request.form()
    url = config.PUBLIC_BASE_URL + "/twilio"
    if request.url.query:
        url += "?" + request.url.query
    if not twilio.signature_ok(url, form, request.headers.get("X-Twilio-Signature", "")):
        return Response(status_code=401)
    event = twilio_event(form)
    if not event:
        return Response("<Response/>", media_type="application/xml")
    msg_id, message = event
    if not inbox.enqueue("twilio", msg_id, message):
        return Response("<Response/>", media_type="application/xml")  # duplicate delivery
    # Handle inline and answer in TwiML (the trial number only allows webhook replies).
    # Twilio waits ~15 s; anything not ready by 13 s finishes in the background.
    token = twilio.start_reply(message["phone"])
    try:
        task = asyncio.ensure_future(inbox.process("twilio", msg_id))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=13)
        except asyncio.TimeoutError:
            pass
        replies = twilio.collected()
    finally:
        twilio.end_reply(token)
    return Response(twilio.twiml(replies), media_type="application/xml")
