"""Sarvam Vision Document AI: read a photo/PDF of a bill or template into Markdown.
Async job flow: create -> poll status -> download ZIP. Best effort: returns '' on any failure.
Docs: https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/how-to/parse.md"""
import asyncio
import io
import zipfile

import httpx

import config
from provider_http import request

BASE = "https://api.sarvam.ai/doc-ai/v1"


async def parse(data: bytes, filename: str, mime: str, language: str = "en-IN") -> str:
    if not config.SARVAM_API_KEY:
        return ""
    h = {"api-subscription-key": config.SARVAM_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            payload = data
            if mime.startswith("image/"):
                # The docs describe images inside a ZIP; wrap to be safe.
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    z.writestr(filename.replace("\\", "/").split("/")[-1], data)
                payload, filename, mime = buf.getvalue(), "pages.zip", "application/zip"
            r = await request(c, "POST", f"{BASE}/job/parse", headers=h, files={"file": (filename, payload, mime)},
                             data={"language": language, "output_format": "md"})
            job = r.json().get("job_id") or r.json().get("id")
            if not job:
                return ""
            for _ in range(12):
                s = (await request(c, "GET", f"{BASE}/job/{job}/status", headers=h)).json()
                st = str(s.get("status", s.get("job_state", ""))).lower()
                if st in {"completed", "partially_completed"}:
                    break
                if st in {"failed", "rejected"}:
                    return ""
                await asyncio.sleep(2)
            else:
                return ""
            url = (await request(c, "GET", f"{BASE}/job/{job}/download-url", headers=h)).json().get("url")
            result = await request(c, "GET", url)
            with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
                return "\n".join(archive.read(n).decode("utf-8", "ignore") for n in archive.namelist()
                                 if n.endswith((".md", ".txt")))
    except Exception as e:
        print("[docai] failed:", type(e).__name__)
        return ""
