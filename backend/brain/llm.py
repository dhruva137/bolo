"""LLM providers behind one function: json_call(system, user) -> dict | None.

Tried in config.LLM_ORDER; a provider without a key is skipped; any error falls through to
the next. Returning None means "use the offline rule planner".
"""
import json
import re

import config
from provider_http import inference_post


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0) if m else text)
    except Exception:
        return None


def _gemini(system: str, user: str) -> dict | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    r = inference_post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=body)
    parts = r.json()["candidates"][0]["content"]["parts"]
    return _extract_json("".join(p.get("text", "") for p in parts))


def _openai_compatible(base: str, headers: dict, model: str, system: str, user: str, extra: dict) -> dict | None:
    body = {"model": model, "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}, **extra}
    r = inference_post(f"{base}/chat/completions", headers=headers, json=body)
    return _extract_json(r.json()["choices"][0]["message"]["content"])


def _sarvam(system: str, user: str) -> dict | None:
    key = config.SARVAM_API_KEY
    return _openai_compatible("https://api.sarvam.ai/v1",
                              {"api-subscription-key": key, "Authorization": f"Bearer {key}"},
                              config.SARVAM_LLM_MODEL, system, user, {"reasoning_effort": "low"})


def _groq(system: str, user: str) -> dict | None:
    return _openai_compatible("https://api.groq.com/openai/v1",
                              {"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                              config.GROQ_LLM_MODEL, system, user, {})


PROVIDERS = {
    "gemini": (lambda: config.GEMINI_API_KEY, _gemini),
    "sarvam": (lambda: config.SARVAM_API_KEY, _sarvam),
    "groq": (lambda: config.GROQ_API_KEY, _groq),
}


def json_call(system: str, user: str) -> tuple[dict | None, str]:
    for name in config.LLM_ORDER:
        has_key, fn = PROVIDERS.get(name, (lambda: "", None))
        if not fn or not has_key():
            continue
        try:
            out = fn(system, user)
            if isinstance(out, dict):
                return out, name
        except Exception as e:
            print(f"[llm] {name} failed: {e}")
    return None, "offline"
