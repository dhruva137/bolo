"""Phone-call escalation through a Bolna voice agent (for people who don't answer on WhatsApp,
or customers on feature phones). Configure the agent and its script in the Bolna dashboard;
we pass the variables. Docs: https://www.bolna.ai/docs/api-reference/calls/make"""
import httpx

import config
import db
from provider_http import request


async def call(phone: str, variables: dict) -> dict:
    if not (config.BOLNA_API_KEY and config.BOLNA_AGENT_ID):
        db.audit("bolo", "call.skipped", {"phone": phone, "reason": "Bolna not configured", **variables})
        return {"status": "skipped"}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await request(c, "POST", "https://api.bolna.ai/call",
                             headers={"Authorization": f"Bearer {config.BOLNA_API_KEY}"},
                             json={"agent_id": config.BOLNA_AGENT_ID, "recipient_phone_number": f"+{phone}",
                                   "user_data": variables})
        out = r.json()
        db.audit("bolo", "call.placed", {"phone": phone, **out})
        return out
    except Exception as e:
        db.audit("bolo", "call.failed", {"phone": phone, "error": str(e)})
        return {"status": "failed", "error": str(e)}
