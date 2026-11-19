"""One real call to each configured provider, with latency. Run from backend/:  python smoke.py

Uses a few paise of credit at most: one short TTS, two short transcriptions, one LLM call,
one translation, one Twilio account read. Nothing is sent to any phone.
"""
import asyncio
import shutil
import time

import httpx

import config
from brain import llm
from voice import audio, stt, translate, tts

ROWS = []


def row(name, ok, ms, detail=""):
    ROWS.append((name, ok, ms, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<22} {ms:>6} ms  {detail}", flush=True)


async def timed(name, coro_or_fn, check=lambda r: bool(r), show=lambda r: str(r)[:70]):
    t = time.perf_counter()
    try:
        result = await coro_or_fn() if asyncio.iscoroutinefunction(coro_or_fn) else coro_or_fn()
        if asyncio.iscoroutine(result):
            result = await result
        row(name, check(result), int((time.perf_counter() - t) * 1000), show(result))
        return result
    except Exception as e:
        row(name, False, int((time.perf_counter() - t) * 1000), f"{type(e).__name__}: {str(e)[:90]}")
        return None


async def main():
    print(f"Channel: {config.status()['whatsapp']} · PUBLIC_BASE_URL={config.PUBLIC_BASE_URL}\n")
    row("ffmpeg", bool(shutil.which("ffmpeg")), 0, shutil.which("ffmpeg") or "not on PATH (bundled imageio-ffmpeg is used)")

    if config.TWILIO_SID:
        async def twilio():
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_SID}.json",
                                auth=(config.TWILIO_SID, config.TWILIO_TOKEN))
            return r
        await timed("twilio account", twilio, lambda r: r.status_code == 200, lambda r: f"HTTP {r.status_code} {r.json().get('status', '')}")

    if config.PUBLIC_BASE_URL.startswith("https://"):
        async def tunnel():
            async with httpx.AsyncClient(timeout=15) as c:
                return await c.get(config.PUBLIC_BASE_URL + "/health")
        await timed("tunnel -> /health", tunnel, lambda r: r.status_code == 200, lambda r: f"HTTP {r.status_code}")

    voice_note = None
    if config.SARVAM_API_KEY:
        voice_note = await timed("sarvam tts (bulbul)", lambda: tts.speak("Ramesh ne chaar sau pachaas ka saman liya", "hi-IN"),
                                 lambda r: bool(r) and r[:4] == b"OggS", lambda r: f"{len(r)} bytes ogg/opus")
        await timed("sarvam translate", lambda: translate.to_lang("Ramesh owes 450 rupees", "kn-IN"),
                    lambda r: bool(r) and r != "Ramesh owes 450 rupees")
    wav = audio.clean(voice_note, "ogg") if voice_note else None
    if wav:
        if config.SARVAM_API_KEY:
            await timed("sarvam stt (saaras)", lambda: stt.sarvam_stt(wav, ["Ramesh", "udhaar"]),
                        lambda h: bool(h.text), lambda h: h.text or h.error)
        if config.GROQ_API_KEY:
            await timed("groq stt (whisper)", lambda: stt.groq_stt(wav), lambda h: bool(h.text), lambda h: h.text or h.error)
        if config.GEMINI_API_KEY:
            await timed("gemini stt", lambda: stt.gemini_stt(wav), lambda h: bool(h.text), lambda h: h.text or h.error)
    elif config.GROQ_API_KEY or config.GEMINI_API_KEY:
        print("     (speech tests need SARVAM_API_KEY to generate a test voice note; skipped)")

    if any([config.GEMINI_API_KEY, config.SARVAM_API_KEY, config.GROQ_API_KEY]):
        def plan():
            return llm.json_call('Return JSON {"tool":"add_credit","name":"...","amount":0} for the request.',
                                 "Ramesh ne 450 ka saman liya")
        await timed("llm planner", plan, lambda r: bool(r and r[0]), lambda r: f"{r[1]} -> {r[0]}")

    failed = [r for r in ROWS if not r[1]]
    print("\n" + ("All configured providers OK." if not failed else f"{len(failed)} check(s) failed: " + ", ".join(r[0] for r in failed)))


if __name__ == "__main__":
    asyncio.run(main())
