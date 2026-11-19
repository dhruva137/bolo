"""Run with python -m unittest tests.test_local_voice from backend/."""
import asyncio
import hashlib
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
import io
import os
import tempfile
import unittest
import wave
from unittest.mock import patch

from voice import audio, local, tts


class SpeechTests(unittest.TestCase):
    @unittest.skipUnless(local.tts_ready(), "install espeakng-loader for the audio codec test")
    def test_free_language_voices_encode_opus(self):
        with patch("config.SARVAM_API_KEY", ""):
            for lang, text in (("kn-IN", "ನಮಸ್ಕಾರ ರಮೇಶ್"), ("hi-IN", "रमेश ने पैसे दिए"),
                               ("en-IN", "Ramesh paid two hundred rupees")):
                note = asyncio.run(tts.speak(text, lang))
                self.assertEqual(note[:4], b"OggS")
                self.assertIn(b"OpusHead", note[:128])

    def test_long_wav_splits_without_losing_frames(self):
        sample = io.BytesIO()
        with wave.open(sample, "wb") as out:
            out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            out.writeframes(b"\0\0" * (16000 * 61))
        counts = []
        for chunk in audio.wav_chunks(sample.getvalue()):
            with wave.open(io.BytesIO(chunk)) as part:
                counts.append(part.getnframes())
        self.assertEqual(counts, [480000, 480000, 16000])


@contextmanager
def temporary_shop():
    with tempfile.TemporaryDirectory() as shop, patch.dict(os.environ, {"BOLO_DATA_DIR": shop}):
        import config
        from fastapi.testclient import TestClient
        from app import app
        for d in ("audio", "docs"):
            (Path(shop) / d).mkdir()
        settings = {"AUDIO_DIR": str(Path(shop) / "audio"), "DOCS_DIR": str(Path(shop) / "docs"),
                    "DB_PATH": str(Path(shop) / "bolo.db"), "DATA_DIR": shop, "SARVAM_API_KEY": "",
                    "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "WHATSAPP_LIVE": False, "TWILIO_LIVE": False}
        connection = sqlite3.connect(settings["DB_PATH"], check_same_thread=False)
        connection.row_factory = sqlite3.Row
        with closing(connection), patch.multiple(config, **settings), patch("db._conn", connection), TestClient(app) as client:
            yield client, Path(shop)


class MissingModelReview(unittest.TestCase):
    def test_original_audio_is_available_for_review_or_discard(self):
        # A laptop can still accept a spoken note before the one-time model download.
        with temporary_shop() as (client, shop), patch("voice.local.stt_ready", return_value=False):
            client.post("/api/seed").raise_for_status()
            phone = "919900000001"
            sample = io.BytesIO()
            with wave.open(sample, "wb") as output:
                output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * 16000)
            response = client.post("/api/simulate/audio", data={"phone": phone},
                                   files={"file": ("note.wav", sample.getvalue(), "audio/wav")})
            response.raise_for_status()
            review = response.json()["review"]
            self.assertEqual(review["text"], "")
            row = client.get("/api/messages", params={"phone": phone}).json()[-1]
            self.assertIsNone(row["meta"]["primary_stt"])
            self.assertEqual(row["meta"]["review_status"], "pending")
            self.assertEqual((shop / "audio" / Path(row["media"]).name).read_bytes(), sample.getvalue())
            discard = {"phone": phone, "message_id": review["message_id"], "discard": True}
            self.assertEqual(client.post("/api/simulate/review", json=discard).json()["status"], "discarded")
            self.assertEqual(client.post("/api/simulate/review", json=discard).json()["status"], "discarded")
            self.assertEqual(len(client.get("/api/messages", params={"phone": phone}).json()), 1)


@unittest.skipUnless(os.environ.get("BOLO_SPEECH_SMOKE") == "1" and local.stt_ready(),
                     "set BOLO_SPEECH_SMOKE=1 after installing the offline model")
class LocalSpeechSmoke(unittest.TestCase):
    def test_one_recorded_note_through_console_route(self):
        # Start the real HTTP application against a temporary shop. Use one CPU model.
        with temporary_shop() as (client, shop):
            self.assertEqual(client.post("/api/seed").status_code, 200)
            speaker = "919900000001"
            wav = local.synthesize_wav("Ramesh paid two hundred rupees for the order. Thank you.", "en-IN")
            before = len(client.get("/api/ledger").json()["entries"])
            start = time.monotonic()
            reply = client.post("/api/simulate/audio", data={"phone": speaker},
                                files={"file": ("sample.wav", wav, "audio/wav")})
            self.assertEqual(reply.status_code, 200, reply.text)
            messages = client.get("/api/messages", params={"phone": speaker}).json()
            received = next(m for m in messages if m["direction"] == "in" and m["kind"] == "voice")
            self.assertEqual(received["meta"]["primary_stt"], "whisper-local")
            self.assertTrue(received["meta"]["engine_a"].strip())
            print("Synthetic English note heard as", repr(received["text"]), flush=True)
            print(f"Transcribed and ready to review in {time.monotonic() - start:.1f} s", flush=True)
            review = reply.json()["review"]
            self.assertEqual(review["message_id"], received["id"])
            self.assertEqual(received["meta"]["review_status"], "pending")
            self.assertEqual(len(client.get("/api/ledger").json()["entries"]), before)
            self.assertFalse(any(m["direction"] == "out" for m in messages))
            corrected = {"phone": speaker, "message_id": received["id"], "text": "Ramesh paid 200 rupees"}
            self.assertEqual(client.post("/api/simulate/review", json=corrected).json()["status"], "used")
            def thread():
                return client.get("/api/messages", params={"phone": speaker}).json()
            size = len(thread())
            self.assertEqual(client.post("/api/simulate/review", json=corrected).json()["status"], "used")
            self.assertEqual(len(thread()), size)
            self.assertEqual(len(client.get("/api/ledger").json()["entries"]), before)
            def tap(prefix, label=""):
                buttons = next(m["buttons"] for m in reversed(thread()) if m["buttons"])
                choice = next(bid for bid, title in buttons if bid.startswith(prefix) and label in title.lower())
                response = client.post("/api/simulate", json={"phone": speaker, "button": choice})
                self.assertEqual(response.status_code, 200)
            tap("pick:", "milk")
            tap("ok:")
            ledger = client.get("/api/ledger").json()
            self.assertEqual(len(ledger["entries"]), before + 1)
            digest = hashlib.sha256(wav).hexdigest()
            saved = next(e for e in ledger["entries"] if e["audio_sha"] == digest)
            self.assertEqual((saved["kind"], saved["amount"]), ("payment", 200))
            self.assertTrue(ledger["verify"]["ok"])
            recorded = next(m for m in thread() if m["id"] == received["id"])
            self.assertEqual(recorded["meta"]["reviewed_text"], corrected["text"])
            self.assertEqual(recorded["meta"]["engine_a"], received["meta"]["engine_a"])
            self.assertEqual(hashlib.sha256((Path(shop) / "audio" / Path(recorded["media"]).name).read_bytes()).hexdigest(), digest)
            spoken = next(m for m in thread() if m["direction"] == "out" and m["kind"] == "voice")
            self.assertIn(b"OpusHead", (Path(shop) / "audio" / Path(spoken["media"]).name).read_bytes()[:128])
            print(f"Confirmed payment 200; recording SHA-256 {digest}; total {time.monotonic() - start:.1f} s", flush=True)
