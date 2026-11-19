"""Sarvam Mayura translation (colloquial, code-mixed friendly). Falls back to the input text.
Docs: https://docs.sarvam.ai/api-reference-docs/text/translate"""
import textwrap

import httpx

import config
from provider_http import request

MAYURA = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}
_cache: dict[tuple[str, str], str] = {}


async def to_lang(text: str, lang: str) -> str:
    if not config.SARVAM_API_KEY or not text or lang not in MAYURA:
        return text
    key = (text, lang)
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            pieces = []
            for part in textwrap.wrap(text, width=1000, replace_whitespace=False, break_on_hyphens=False):
                r = await request(c, "POST", "https://api.sarvam.ai/translate", replay_safe=True,
                                  headers={"api-subscription-key": config.SARVAM_API_KEY},
                                  json={"input": part, "source_language_code": "auto", "target_language_code": lang,
                                        "model": "mayura:v1", "mode": "modern-colloquial",
                                        "numerals_format": "international"})
                value = r.json().get("translated_text")
                if not value:
                    return text
                pieces.append(value)
        out = " ".join(pieces)
    except Exception as e:
        print("[translate] failed:", type(e).__name__)
        return text
    if len(_cache) >= 256:
        _cache.pop(next(iter(_cache)))
    _cache[key] = out
    return out
