"""Speech-to-text: two independent engines so names and numbers can be cross-checked.

A: Sarvam Saaras v4 (codemix, auto language ID, keyterms = this shop's names/products)
B: Groq Whisper large-v3-turbo (segment log-probs give a confidence signal)
Docs: https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe
      https://console.groq.com/docs/speech-to-text
"""
import asyncio
import json
import wave
from dataclasses import dataclass, field

import httpx

import config
from provider_http import request
from voice import audio, local


def available() -> bool:
    return bool(config.SARVAM_API_KEY or config.GROQ_API_KEY or config.GEMINI_API_KEY or local.stt_ready())


@dataclass
class Heard:
    engine: str
    text: str
    language: str | None = None
    confidence: float | None = None  # 0..1, engine-specific
    error: str | None = None
    extra: dict = field(default_factory=dict)


async def sarvam_stt(wav: bytes, keyterms: list[str] | None = None) -> Heard:
    if not config.SARVAM_API_KEY:
        return Heard("sarvam", "", error="unconfigured")
    data = {"model": "saaras:v4", "mode": "codemix", "language_code": "unknown"}
    if keyterms:
        data["keyterms"] = json.dumps([k[:64] for k in keyterms[:50]])
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await request(c, "POST",
                "https://api.sarvam.ai/speech-to-text",
                replay_safe=True, headers={"api-subscription-key": config.SARVAM_API_KEY},
                files={"file": ("note.wav", wav, "audio/wav")},
                data=data,
            )
        r.raise_for_status()
        j = r.json()
        return Heard("sarvam", j.get("transcript", ""), j.get("language_code"), j.get("language_probability"))
    except Exception as e:  # never let one engine kill the pipeline
        return Heard("sarvam", "", error=str(e))


async def groq_stt(wav: bytes, language: str | None = None) -> Heard:
    if not config.GROQ_API_KEY:
        return Heard("groq", "", error="unconfigured")
    data = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json", "temperature": "0"}
    if language:
        data["language"] = language.split("-")[0]  # "hi-IN" -> "hi"
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await request(c, "POST",
                "https://api.groq.com/openai/v1/audio/transcriptions",
                replay_safe=True, headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                files={"file": ("note.wav", wav, "audio/wav")},
                data=data,
            )
        r.raise_for_status()
        j = r.json()
        segs = j.get("segments") or []
        # avg_logprob is ~0 for confident speech and drops toward -1 or lower for noise/guessing
        conf = None
        if segs:
            avg = sum(s.get("avg_logprob", -1.0) for s in segs) / len(segs)
            conf = max(0.0, min(1.0, 1.0 + avg))
        return Heard("groq", j.get("text", "").strip(), j.get("language"), conf, extra={"segments": len(segs)})
    except Exception as e:
        return Heard("groq", "", error=str(e))


async def gemini_stt(wav: bytes) -> Heard:
    """Third engine: Gemini audio understanding (free tier). Used only when the others fail."""
    if not config.GEMINI_API_KEY:
        return Heard("gemini", "", error="no key")
    import base64
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await request(c, "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
                replay_safe=True, headers={"x-goog-api-key": config.GEMINI_API_KEY},
                json={"contents": [{"parts": [
                    {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav).decode()}},
                    {"text": "Transcribe this Indian voice note exactly as spoken (keep code-mixing, Latin script for English "
                             "words). Return only the transcript."}]}]})
        r.raise_for_status()
        text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]).strip()
        return Heard("gemini", text)
    except Exception as e:
        return Heard("gemini", "", error=str(e))


async def _whole_note(engine, name, wav, *args):
    """A failed chunk invalidates this engine's transcript of the transaction."""
    pieces = []
    try:
        for chunk in audio.wav_chunks(wav):
            heard = await engine(chunk, *args)
            if not heard.text:
                return heard
            pieces.append(heard)
    except (wave.Error, EOFError, ValueError):
        return Heard(name, "", error="Invalid PCM audio")
    if not pieces:
        return Heard(name, "", error="Empty audio")
    first = pieces[0]
    confidences = [p.confidence for p in pieces if p.confidence is not None]
    return Heard(name, " ".join(p.text for p in pieces), first.language,
                 min(confidences) if confidences else None, extra={"chunks": len(pieces)})


async def hear_twice(wav: bytes, keyterms: list[str] | None = None) -> tuple[Heard, Heard]:
    """Run configured primary engines, then Gemini or the local CPU recognizer."""
    a, b = await asyncio.gather(_whole_note(sarvam_stt, "sarvam", wav, keyterms),
                                _whole_note(groq_stt, "groq", wav))
    if a.text and b.text:
        return a, b
    if config.GEMINI_API_KEY:
        fallback = await _whole_note(gemini_stt, "gemini", wav)
        if fallback.text:
            return (a, fallback) if a.text else (fallback, b)
    if not a.text and not b.text and local.stt_ready():
        try:
            text, lang, confidence = await asyncio.to_thread(local.transcribe, wav)
            return Heard("whisper-local", text, lang, confidence), b
        except Exception as error:
            print("[stt] local recognition failed:", type(error).__name__)
            return Heard("whisper-local", "", error=type(error).__name__), b
    return a, b
