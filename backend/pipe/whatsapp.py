"""WhatsApp Cloud API: receive messages, download media, send replies.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/
"""
from functools import lru_cache
import hashlib
import hmac
import os

import httpx
from provider_http import request

GRAPH = "https://graph.facebook.com/v27.0"
TOKEN = os.environ.get("WA_TOKEN", "")
PHONE_ID = os.environ.get("WA_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "bolo-verify")
APP_SECRET = os.environ.get("WA_APP_SECRET")

@lru_cache(maxsize=1)
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


def _auth() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}


def signature_ok(raw_body: bytes, header: str) -> bool:
    """Check X-Hub-Signature-256 when an app secret is configured."""
    if not APP_SECRET or not header.isascii():
        return False
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header or "", expected)


async def _send(payload: dict) -> dict:
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", **payload}
    r = await request(client(), "POST", f"{GRAPH}/{PHONE_ID}/messages", headers=_auth(), json=payload)
    return r.json()


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Return (bytes, mime_type). The media URL expires in ~5 minutes, so fetch immediately."""
    meta = (await request(client(), "GET", f"{GRAPH}/{media_id}", headers=_auth())).json()
    r = await request(client(), "GET", meta["url"], headers=_auth())
    return r.raise_for_status().content, meta.get("mime_type", "")


async def upload_media(data: bytes, mime: str, filename: str) -> str:
    r = await request(client(), "POST",
        f"{GRAPH}/{PHONE_ID}/media",
        headers=_auth(),
        data={"messaging_product": "whatsapp", "type": mime},
        files={"file": (filename, data, mime)},
        replay_safe=True,
    )
    return r.raise_for_status().json()["id"]


async def mark_read_typing(message_id: str) -> None:
    """Blue ticks + 'typing…' while we process (shows up to 25 s)."""
    await request(client(), "POST",
        f"{GRAPH}/{PHONE_ID}/messages",
        headers=_auth(),
        json={
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        },
        replay_safe=True,
    )


async def send_text(to: str, body: str) -> dict:
    return await _send({"to": to, "type": "text", "text": {"body": body[:4096]}})


async def send_buttons(to: str, body: str, buttons: list[tuple[str, str]]) -> dict:
    """buttons: up to 3 (id, title); titles are cut to WhatsApp's 20-char limit."""
    btns = [{"type": "reply", "reply": {"id": i[:256], "title": t[:20]}} for i, t in buttons[:3]]
    return await _send({
        "to": to,
        "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body[:1024]}, "action": {"buttons": btns}},
    })


async def send_voice(to: str, ogg_opus: bytes) -> dict:
    """Send as a native voice note. Audio must be OGG/Opus mono (see voice/audio.py)."""
    media_id = await upload_media(ogg_opus, "audio/ogg", "bolo.ogg")
    return await _send({"to": to, "type": "audio", "audio": {"id": media_id, "voice": True}})


async def send_document(to: str, pdf: bytes, filename: str, caption: str = "") -> dict:
    media_id = await upload_media(pdf, "application/pdf", filename)
    return await _send({
        "to": to,
        "type": "document",
        "document": {"id": media_id, "filename": filename, "caption": caption},
    })
