"""Offline checks for the external speech API contracts and failure handling."""
import io
import unittest
import wave
import zipfile
from unittest.mock import AsyncMock, patch

import httpx

from voice import docai, stt, translate, tts


def pcm(seconds=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as w:
        w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        w.writeframes(b"\0\0" * (16000 * seconds))
    return output.getvalue()


def client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class ProviderVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sarvam_sends_keyterms_on_each_chunk(self):
        seen = []

        def serve(req):
            seen.append(req.read())
            return httpx.Response(200, json={"transcript": str(len(seen)), "language_code": "kn-IN"})

        client = client_with(serve)
        with patch("config.SARVAM_API_KEY", "test"), patch("httpx.AsyncClient", return_value=client):
            one = await stt.sarvam_stt(pcm(), ["New Delhi", "Ramesh"])
        self.assertEqual(one.text, "1")
        self.assertIn(b'name="keyterms"', seen[0])
        self.assertIn(b'["New Delhi", "Ramesh"]', seen[0])

        engine = AsyncMock(side_effect=[stt.Heard("s", "one"), stt.Heard("s", "two")])
        complete = await stt._whole_note(engine, "s", pcm(31))
        self.assertEqual(complete.text, "one two")
        engine = AsyncMock(side_effect=[stt.Heard("s", "one"), stt.Heard("s", "", error="timeout")])
        missing = await stt._whole_note(engine, "s", pcm(31))
        self.assertEqual(missing.text, "")

    async def test_gemini_only_is_reachable_and_key_stays_in_header(self):
        def serve(req):
            self.assertEqual(req.headers["x-goog-api-key"], "test")
            self.assertFalse(req.url.query)
            self.assertIn(b'"mimeType":"audio/wav"', req.read())
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "heard"}]}}]})

        client = client_with(serve)
        with patch("config.SARVAM_API_KEY", ""), patch("config.GROQ_API_KEY", ""), \
                patch("config.GEMINI_API_KEY", "test"), patch("httpx.AsyncClient", return_value=client):
            self.assertTrue(stt.available())
            a, b = await stt.hear_twice(pcm())
        self.assertEqual((a.engine, a.text, b.text), ("gemini", "heard", ""))

    async def test_bulbul_returns_ogg_opus_from_decoded_audio(self):
        import base64
        import json
        from voice.audio import _ffmpeg
        audio = _ffmpeg(pcm(), "wav", "mp3", ["-codec:a", "libmp3lame"])
        def serve(req):
            body = json.loads(req.read())
            self.assertEqual((body["model"], body["speaker"], body["output_audio_codec"]), ("bulbul:v3", "shubh", "mp3"))
            return httpx.Response(200, json={"audios": [base64.b64encode(audio).decode()]})
        client = client_with(serve)
        with patch("httpx.AsyncClient", return_value=client):
            result = await tts._bulbul("sample", "kn-IN", "shubh")
        self.assertEqual(result[:4], b"OggS")
        self.assertIn(b"OpusHead", result[:128])

    async def test_translation_preserves_tail_and_retries_after_outage(self):
        long_text = "sample " * 160 + "last"
        translate._cache.clear()
        from json import loads
        def translate_ok(req):
            source = loads(req.read())["input"]
            self.assertLessEqual(len(source), 1000)
            return httpx.Response(200, json={"translated_text": source.upper()})
        clients = [client_with(lambda req: httpx.Response(401)), client_with(translate_ok)]
        with patch("config.SARVAM_API_KEY", "test"), patch("httpx.AsyncClient", side_effect=clients):
            self.assertEqual(await translate.to_lang(long_text, "kn-IN"), long_text)
            self.assertEqual(await translate.to_lang(long_text, "kn-IN"), long_text.upper())

    async def test_docai_waits_for_completed_job_and_downloads_plain_zip(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("bill/bill.md", "Total 450")
        paths = []
        def serve(req):
            paths.append(req.url.path)
            if req.url.path.endswith("/parse"):
                self.assertIn(b'name="output_format"', req.read())
                self.assertIn(b"pages.zip", req.read())
                return httpx.Response(200, json={"job_id": "1"})
            if req.url.path.endswith("/status"):
                return httpx.Response(200, json={"status": "partially_completed"})
            if req.url.path.endswith("/download-url"):
                return httpx.Response(200, json={"url": "https://storage.invalid/result"})
            self.assertNotIn("api-subscription-key", req.headers)
            return httpx.Response(200, content=archive.getvalue())
        client = client_with(serve)
        with patch("config.SARVAM_API_KEY", "test"), patch("httpx.AsyncClient", return_value=client):
            self.assertEqual(await docai.parse(b"image", "bill.jpg", "image/jpeg"), "Total 450")
        self.assertEqual(len(paths), 4)

    async def test_docai_times_out_before_any_download(self):
        seen = []
        def serve(req):
            seen.append(req.url.path)
            return httpx.Response(200, json={"job_id": "1", "status": "running"})
        client = client_with(serve)
        with patch("config.SARVAM_API_KEY", "test"), patch("httpx.AsyncClient", return_value=client), \
                patch("voice.docai.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual(await docai.parse(b"pdf", "bill.pdf", "application/pdf"), "")
        self.assertFalse(any("download" in path for path in seen))
