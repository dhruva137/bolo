"""Public WhatsApp entry point. Keep the owner console on a separate loopback port."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

import config
import db
from app import pay_page
from pipe import webhooks


@asynccontextmanager
async def lifespan(app):
    # The owner console and gateway share the same BOLO_DATA_DIR. Only the console
    # runs scheduled reminders and retries media downloads after a restart.
    db.init()
    yield


app = FastAPI(lifespan=lifespan, openapi_url=None)
app.include_router(webhooks.router)


@app.api_route("/share/{token}", methods=["GET", "HEAD"])
async def shared_resource(token: str):
    row = db.q1("SELECT kind,target FROM shared_links WHERE token=? AND expires_at>?", (token, db.now()))
    if not row:
        raise HTTPException(404)
    target = json.loads(row["target"])
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if row["kind"] == "pay":
        return HTMLResponse(await pay_page(target["contact_id"], target["amount"]), headers=headers)
    directory = {"audio": config.AUDIO_DIR, "file": config.DOCS_DIR}.get(row["kind"])
    if not directory:
        raise HTTPException(404)
    path = Path(directory) / Path(target).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=path.name, headers=headers)
