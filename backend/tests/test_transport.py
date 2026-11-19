"""WhatsApp transport contracts with synthetic phones and in-process HTTP fixtures.

Run from backend with python -m unittest tests.test_transport. No network is used.
"""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import sqlite3
import tempfile
import unittest
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient
from PIL import Image

import config
import db
import gateway
import seed
from core import ledger
from pipe import inbox, messenger, twilio, whatsapp
from voice import audio, tts

OWNER = "919900000001"
FIXTURE_PHONE_ID = "10000000001"
FIXTURE_ACCOUNT = "AC" + "0" * 32
MESSAGE_PATH = f"/2010-04-01/Accounts/{FIXTURE_ACCOUNT}/Messages/"
MEDIA_URL = f"https://api.twilio.com{MESSAGE_PATH}SM{'1'*32}/Media/ME{'2'*32}"
PUBLIC = "https://fixture.invalid"


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        self.stack.enter_context(patch.object(db, "_conn", conn))
        self.stack.enter_context(patch.multiple(
            config, AUDIO_DIR=str(temp), DOCS_DIR=str(temp), PUBLIC_BASE_URL=PUBLIC,
            WHATSAPP_LIVE=False, TWILIO_LIVE=False, WA_PHONE_NUMBER_ID=FIXTURE_PHONE_ID,
            TWILIO_SID=FIXTURE_ACCOUNT, TWILIO_TOKEN="dummy-twilio",
            LLM_ORDER=[], SARVAM_API_KEY="", GROQ_API_KEY="", GEMINI_API_KEY="",
        ))
        self.stack.enter_context(patch.multiple(whatsapp, PHONE_ID=FIXTURE_PHONE_ID,
                                               TOKEN="dummy-access", APP_SECRET="dummy-meta"))
        seed.run()
        db.set_setting("voice_replies", "0")
        self.client = self.stack.enter_context(TestClient(gateway.app))
        self.requests = []
        self.media_bytes = b""
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.mock_provider))
        self.addCleanup(lambda: asyncio.run(http.aclose()))
        self.stack.enter_context(patch.object(whatsapp, "client", return_value=http))
        self.stack.enter_context(patch.object(twilio, "client", return_value=http))

    def mock_provider(self, req):
        self.requests.append(req)
        path = req.url.path
        if req.method == "GET":
            if path.endswith("/123"):
                return httpx.Response(200, json={"url": "https://fixture.invalid/voice", "mime_type": "audio/ogg"})
            if path == "/voice" or req.url == httpx.URL(MEDIA_URL):
                return httpx.Response(200, content=self.media_bytes, headers={"Content-Type": "audio/ogg"})
        if req.method == "POST":
            if path.endswith("/media"):
                return httpx.Response(200, json={"id": "uploaded-media-id"})
            if path.endswith(("/messages", "/Messages.json")):
                return httpx.Response(200, json={"messages": [{"id": "accepted-fixture"}]})
        self.fail(f"Unexpected provider request {req.method} {path}")

    def signed_meta(self, body):
        raw = json.dumps(body).encode()
        signature = hmac.new(b"dummy-meta", raw, hashlib.sha256).hexdigest()
        return self.client.post("/webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=" + signature})

    def meta(self, message_id, kind, payload):
        value = {"metadata": {"phone_number_id": FIXTURE_PHONE_ID}, "messages": [
            {"id": message_id, "from": OWNER, "type": kind, kind: payload}
        ]}
        response = self.signed_meta({"entry": [{"changes": [{"value": value}]}]})
        self.assertEqual(response.status_code, 200)

    def twilio(self, message_id, **fields):
        form = {"From": "whatsapp:+" + OWNER, "To": config.TWILIO_FROM, "MessageSid": message_id,
                "AccountSid": FIXTURE_ACCOUNT, "NumMedia": "0", **fields}
        signed = PUBLIC + "/twilio" + "".join(k + form[k] for k in sorted(form))
        signature = base64.b64encode(hmac.digest(b"dummy-twilio", signed.encode(), "sha1")).decode()
        response = self.client.post("/twilio", data=form, headers={"X-Twilio-Signature": signature})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith("<Response"))  # replies come back as TwiML
        return response.text

    def outgoing(self, phone=OWNER):
        return db.q("SELECT * FROM messages WHERE direction='out' AND phone=? ORDER BY id", (phone,))

    def test_meta_button_commits_once(self):
        config.WHATSAPP_LIVE = True
        start = db.q1("SELECT count(*) n FROM ledger")["n"]
        for _ in range(2):
            self.meta("wamid.in-1", "text", {"body": "Fatima 300 udhaar"})
        buttons = json.loads(self.outgoing()[-1]["buttons"])
        choice = next(value for value, _ in buttons if value.startswith("ok:"))
        for _ in range(2):
            self.meta("wamid.in-2", "interactive", {"type": "button_reply", "button_reply": {"id": choice}})
        self.assertEqual(db.q1("SELECT count(*) n FROM ledger")["n"], start + 1)
        self.assertTrue(ledger.verify_chain()["ok"])
        self.assertEqual(len(db.q("SELECT 1 FROM webhook_inbox WHERE state='done'")), 2)
        sent = [json.loads(req.content) for req in self.requests if req.url.path.endswith("/messages")]
        self.assertIn(choice, [b["reply"]["id"] for event in sent if event.get("type") == "interactive"
                               for b in event["interactive"]["action"]["buttons"]])
        self.assertTrue(all(event.get("to", OWNER) == OWNER for event in sent))

    def test_twilio_numbered_reply_commits_once(self):
        config.TWILIO_LIVE = True
        start = db.q1("SELECT count(*) n FROM ledger")["n"]
        twiml = self.twilio("SM-one", Body="Fatima 300 udhaar")
        # The trial number only accepts webhook replies: the numbered card is in the TwiML, not an API call.
        self.assertIn("<Message><Body>", twiml)
        self.assertIn("1.", twiml)
        self.assertFalse([r for r in self.requests if r.url.path.endswith("/Messages.json")])
        for _ in range(2):
            self.twilio("SM-two", Body="1")
        self.assertEqual(db.q1("SELECT count(*) n FROM ledger")["n"], start + 1)
        self.assertTrue(ledger.verify_chain()["ok"])

    def test_signatures_and_unexpected_callback_shapes(self):
        self.assertEqual(self.client.post("/webhook", json={}).status_code, 503)
        self.assertEqual(self.client.post("/twilio", data={"Body": "hi"}).status_code, 503)
        config.WHATSAPP_LIVE = config.TWILIO_LIVE = True
        self.assertEqual(self.client.post("/webhook", json={}).status_code, 401)
        self.assertEqual(self.client.post("/twilio", data={"Body": "hi"}).status_code, 401)
        self.assertEqual(self.signed_meta(None).status_code, 400)
        malformed = {"entry": [None, {"changes": [1, {"value": {"messages": [False, {}]}}]}]}
        self.assertEqual(self.signed_meta(malformed).status_code, 200)
        self.twilio("SM-empty", NumMedia="unknown")
        self.assertEqual(db.q("SELECT * FROM webhook_inbox"), [])
        self.assertEqual(self.requests, [])
        challenge = {"hub.mode": "subscribe", "hub.verify_token": whatsapp.VERIFY_TOKEN, "hub.challenge": "321"}
        self.assertEqual(self.client.get("/webhook", params=challenge).text, "321")

    def make_voice_fixture(self):
        wav = io.BytesIO()
        with wave.open(wav, "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", ""))
            stream.writeframes(b"\x00\x00" * 1600)
        return audio.to_voice_note(wav.getvalue(), "wav")

    def test_both_transports_fetch_audio_and_send_voice_and_pdf(self):
        self.media_bytes = self.make_voice_fixture()
        self.assertTrue(self.media_bytes.startswith(b"OggS"))
        self.assertIn(b"OpusHead", self.media_bytes)
        path = Path(config.DOCS_DIR) / "quotation.pdf"
        Image.new("RGB", (16, 16), "white").save(path, "PDF")
        pdf = path.read_bytes()
        for provider in ("meta", "twilio"):
            config.WHATSAPP_LIVE = provider == "meta"
            config.TWILIO_LIVE = provider == "twilio"
            self.requests.clear()
            # Capture the handoff before speech processing. Verify the bytes and addressing.
            with patch.object(inbox.agent, "handle", new_callable=AsyncMock) as handle:
                if provider == "meta":
                    self.meta("wamid.voice", "audio", {"id": "123", "mime_type": "audio/ogg; codecs=opus"})
                else:
                    self.twilio("SM-voice", NumMedia="1", MediaUrl0=MEDIA_URL, MediaContentType0="audio/ogg")
                args = handle.await_args.kwargs
                self.assertEqual((args["phone"], args["kind"], args["audio_ext"]), (OWNER, "audio", "ogg"))
                self.assertEqual(args["audio_bytes"], self.media_bytes)
            with patch.object(tts, "available", return_value=True), patch.object(tts, "speak", return_value=self.media_bytes):
                asyncio.run(messenger.say(OWNER, "Confirmed", "en-IN", voice=True))
            asyncio.run(messenger.send_file(OWNER, str(path), path.name))
            self.assertEqual([json.loads(m["meta"])["delivery"] for m in self.outgoing()[-3:]], ["accepted"] * 3)
            if provider == "meta":
                uploads = [r.content for r in self.requests if r.url.path.endswith("/media")]
                self.assertIn(self.media_bytes, uploads[0])
                self.assertIn(pdf, uploads[1])
                events = [json.loads(r.content) for r in self.requests if r.url.path.endswith("/messages")]
                self.assertIn({"voice": True, "id": "uploaded-media-id"}, [e.get("audio") for e in events])
                self.assertEqual(events[-1]["document"]["filename"], "quotation.pdf")
            else:
                forms = [parse_qs(r.content.decode()) for r in self.requests if r.method == "POST"]
                links = [urlsplit(f["MediaUrl"][0]).path for f in forms if "MediaUrl" in f]
                self.assertEqual([self.client.get(link).content for link in links], [self.media_bytes, pdf])

    def test_download_retry_and_interrupted_action(self):
        config.WHATSAPP_LIVE = True
        with patch.object(whatsapp, "download_media", side_effect=TimeoutError):
            self.meta("wamid.retry", "audio", {"id": "123"})
        row = db.q1("SELECT * FROM webhook_inbox WHERE message_id='wamid.retry'")
        self.assertEqual((row["attempts"], row["state"]), (1, "queued"))
        db.run("UPDATE webhook_inbox SET next_attempt=0")
        with patch.object(whatsapp, "download_media", return_value=(b"fixture", "audio/ogg")), \
                patch.object(inbox.agent, "handle", side_effect=ValueError) as handle:
            asyncio.run(inbox.resume())
            asyncio.run(inbox.resume())
            self.assertEqual(handle.await_count, 1)
        self.assertEqual(db.q1("SELECT state FROM webhook_inbox")["state"], "review")

    def test_expiring_resource_and_service_window(self):
        self.assertEqual(set(gateway.app.openapi()["paths"]), {"/webhook", "/twilio", "/share/{token}"})
        config.WHATSAPP_LIVE = True
        asyncio.run(messenger.say(OWNER, "Hello", "en-IN", voice=False))
        self.assertEqual(json.loads(self.outgoing()[-1]["meta"])["delivery"], "outside_service_window")
        self.assertEqual(self.requests, [])
        db.set_setting("upi_id", "fixture@upi")
        db.set_setting("shop_name", "Seeds & Grain")
        owner = db.q1("SELECT id FROM contacts WHERE phone=?", (OWNER,))
        url = urlsplit(messenger.payment_url(owner["id"], 450)).path
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Seeds &amp; Grain", page.text)
        self.assertIn("am=450.00", page.text)
        db.run("UPDATE shared_links SET expires_at=0")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_send_failure_is_recorded(self):
        config.WHATSAPP_LIVE = True
        inbox.enqueue("meta", "wamid.window", {"kind": "text", "text": "hi", "phone": OWNER})
        failure = httpx.Response(400, request=httpx.Request("POST", "https://fixture.invalid/messages"))
        with patch.object(whatsapp, "send_text", side_effect=httpx.HTTPStatusError(
                "Rejected", request=failure.request, response=failure)):
            asyncio.run(messenger.say(OWNER, "Test", "en-IN", voice=False))
        meta = json.loads(self.outgoing()[-1]["meta"])
        self.assertEqual((meta["provider"], meta["delivery"], meta["http_status"]), ("meta", "failed", 400))


if __name__ == "__main__":
    unittest.main()
