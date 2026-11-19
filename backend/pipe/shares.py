"""Expiring unguessable links for the media or payment page sent to a recipient."""
import json
import secrets

import config
import db


def make(kind, target):
    token = secrets.token_urlsafe(32)
    with db.tx() as conn:
        conn.execute("DELETE FROM shared_links WHERE expires_at<=?", (db.now(),))
        conn.execute("INSERT INTO shared_links VALUES (?,?,?,?)",
                     (token, kind, json.dumps(target), db.now() + 86400))
    return f"{config.PUBLIC_BASE_URL}/share/{token}"
