"""Text-to-speech with Sarvam Bulbul, returned as a WhatsApp-ready voice note.

Docs: https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert
Bulbul cannot output Opus, so we request mp3 and convert with ffmpeg.
"""
import base64
import asyncio

import httpx

from voice.audio import to_voice_note
from voice import local
from provider_http import request

import config

# Sarvam STT returns codes like "kn-IN"; Bulbul v3 covers these 11.
BULBUL_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}


def available() -> bool:
    return bool(config.SARVAM_API_KEY) or local.tts_ready()


async def _bulbul(text: str, language: str, speaker: str) -> bytes:
    lang = language if language in BULBUL_LANGS else "hi-IN"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await request(c, "POST",
            "https://api.sarvam.ai/text-to-speech",
            replay_safe=True, headers={"api-subscription-key": config.SARVAM_API_KEY},
            json={
                "text": text[:2500],
                "language_code": lang,
                "model": "bulbul:v3",
                "speaker": speaker,
                "pace": 1.0,
                "speech_sample_rate": 24000,
                "output_audio_codec": "mp3",
            },
        )
    audio = base64.b64decode(r.json()["audios"][0], validate=True)
    return await asyncio.to_thread(to_voice_note, audio, "mp3")


async def speak(text: str, language: str = "hi-IN", speaker: str = "shubh") -> bytes:
    """Return mono OGG/Opus for the simulator and WhatsApp."""
    if config.SARVAM_API_KEY:
        try:
            return await _bulbul(text, language, speaker)
        except Exception:
            if not local.tts_ready():
                raise
    wav = await asyncio.to_thread(local.synthesize_wav, text, language)
    return await asyncio.to_thread(to_voice_note, wav, "wav")
