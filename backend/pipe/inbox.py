"""Durable webhook receipts. A provider redelivery must never repeat a shop action."""
import json

import db
from brain import agent
from pipe import twilio, whatsapp


def enqueue(provider, message_id, message):
    # The provider ID is unique before HTTP success is returned, including across processes.
    with db.tx() as conn:
        result = conn.execute("INSERT OR IGNORE INTO webhook_inbox(provider,message_id,payload,phone,received_at) "
                              "VALUES (?,?,?,?,?)",
                              (provider, message_id, json.dumps(message, ensure_ascii=False), message["phone"], db.now()))
        return result.rowcount == 1


async def prepare(provider, message):
    """All potentially retryable reads happen before any shop action."""
    args = dict(message)
    resource = args.pop("resource", "")
    if not resource:
        return args
    mime = args.pop("mime", "")
    if provider == "meta":
        data, detected = await whatsapp.download_media(resource)
        mime = detected or mime
    else:
        data = await twilio.download_media(resource)
    if args["kind"] == "audio":
        formats = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
                   "audio/aac": "aac", "audio/amr": "amr", "audio/wav": "wav", "audio/webm": "webm"}
        args.update(audio_bytes=data, audio_ext=formats.get(mime.split(";")[0].strip(), "ogg"))
    else:
        args.update(media=data, mime=mime)
    return args


async def process(provider, message_id):
    key = (provider, message_id)
    with db.tx() as conn:
        # A crashed media download can be retried. The attempt number identifies its worker.
        t = db.now()
        changed = conn.execute("UPDATE webhook_inbox SET state='fetching', attempts=attempts+1, next_attempt=? "
                               "WHERE provider=? AND message_id=? AND state IN ('queued','fetching') "
                               "AND next_attempt<=?", (t + 180, *key, t))
        if not changed.rowcount:
            return
        row = db.q1("SELECT attempts,payload FROM webhook_inbox WHERE provider=? AND message_id=?", key)
    attempt = row["attempts"]
    try:
        args = await prepare(provider, json.loads(row["payload"]))
    except Exception as exc:
        state = "queued" if attempt < 3 else "failed"
        db.run("UPDATE webhook_inbox SET state=?,next_attempt=? WHERE provider=? AND message_id=? AND attempts=? AND state='fetching'",
               (state, db.now() + 30, *key, attempt))
        db.audit(provider, "webhook_download", {"message_id": message_id, "state": state, "error": type(exc).__name__})
        return

    with db.tx() as conn:
        changed = conn.execute("UPDATE webhook_inbox SET state='applying' WHERE provider=? AND message_id=? "
                               "AND attempts=? AND state='fetching'", (*key, attempt))
        if not changed.rowcount:
            return
    # After this boundary an exception could follow an actual ledger write or send.
    # Never replay it blindly. Leave an auditable receipt for the owner to reconcile.
    try:
        if provider == "meta":
            try:
                await whatsapp.mark_read_typing(message_id)
            except Exception:
                pass  # typing is best effort
        await agent.handle(**args)
    except Exception as exc:
        db.run("UPDATE webhook_inbox SET state='review' WHERE provider=? AND message_id=? AND state='applying'", key)
        db.audit(provider, "webhook_needs_review", {"message_id": message_id, "error": type(exc).__name__})
        return
    db.run("UPDATE webhook_inbox SET state='done',payload='{}' WHERE provider=? AND message_id=? AND state='applying'", key)


async def resume():
    rows = db.q("SELECT provider,message_id FROM webhook_inbox WHERE state IN ('queued','fetching') "
                "AND next_attempt<=? ORDER BY rowid LIMIT 25", (db.now(),))
    for row in rows:
        await process(row["provider"], row["message_id"])
