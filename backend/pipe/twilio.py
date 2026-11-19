"""Official Twilio sandbox transport. The sandbox renders reply buttons as numbered text."""
import base64
from functools import lru_cache
import hashlib
import hmac
import re
from urllib.parse import urlsplit

import httpx

import config
from provider_http import request

@lru_cache(maxsize=1)
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


def signature_ok(public_url, form, signature):
    """Twilio signs the exact callback URL followed by the sorted form names/values."""
    if not config.TWILIO_TOKEN or not signature.isascii():
        return False
    parts = [public_url]
    for key in sorted(form):
        for value in sorted(set(form.getlist(key))):
            parts.extend((key, value))
    digest = hmac.digest(config.TWILIO_TOKEN.encode(), "".join(parts).encode(), hashlib.sha1)
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def valid_media_url(url):
    """Only the account's canonical Media resource receives its Basic credentials."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    sid = re.escape(config.TWILIO_SID)
    path = rf"/2010-04-01/Accounts/{sid}/Messages/(?:SM|MM)[a-fA-F0-9]{{32}}/Media/ME[a-fA-F0-9]{{32}}"
    return parts.scheme == "https" and parts.netloc == "api.twilio.com" and bool(re.fullmatch(path, parts.path))


async def download_media(url):
    if not valid_media_url(url):
        raise ValueError("Unrecognised Twilio media resource")
    response = await request(client(), "GET", url, auth=(config.TWILIO_SID, config.TWILIO_TOKEN),
                             follow_redirects=True)
    return response.content


# Twilio's trial number rejects free-form API sends (error 21654, "ContentSid Required") but accepts
# replies returned in the webhook's TwiML. While a webhook is being handled, replies to that sender
# are collected here and returned as <Message> elements instead of separate API calls.
import contextvars
from xml.sax.saxutils import escape

_reply = contextvars.ContextVar("twilio_reply", default=None)


# Replies that finished after the webhook already answered (e.g. slow document reading). The trial
# number cannot push them, so they ride along with the sender's next webhook response.
_late: dict[str, list] = {}


def start_reply(phone):
    return _reply.set({"phone": phone, "messages": _late.pop(phone, []), "closed": False})


def collected():
    buf = _reply.get()
    return list(buf["messages"]) if buf else []


def end_reply(token):
    buf = _reply.get()
    if buf is not None:
        buf["closed"] = True
    _reply.reset(token)


def twiml(messages):
    parts = []
    for body, media in messages[-10:]:
        inner = f"<Body>{escape(body[:1500])}</Body>" if body else ""
        if media:
            inner += f"<Media>{escape(media)}</Media>"
        parts.append(f"<Message>{inner}</Message>")
    return "<Response>" + "".join(parts) + "</Response>" if parts else "<Response/>"


async def send(phone, body, media_url=""):
    buf = _reply.get()
    if buf is not None and buf["phone"] == phone:
        if buf["closed"]:  # webhook already answered; deliver with the next inbound message
            _late.setdefault(phone, []).append((body, media_url))
        else:
            buf["messages"].append((body, media_url))
        return None
    fields = {"From": config.TWILIO_FROM, "To": f"whatsapp:+{phone}", "Body": body[:1500]}
    if media_url:
        fields["MediaUrl"] = media_url
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_SID}/Messages.json"
    return await request(client(), "POST", url, auth=(config.TWILIO_SID, config.TWILIO_TOKEN), data=fields)
