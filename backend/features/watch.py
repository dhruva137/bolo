"""Summarize the last incoming note using explicit wording, without another API call."""
import re

DISPUTE = re.compile(r"\b(?:galat|wrong|dispute|incorrect)\b|गलत|ಗಲತ|ತಪ್ಪು", re.I)
URGENT = re.compile(r"\b(?:urgent|urgently|asap|jaldi|immediately)\b|जल्दी|तुरंत|ಬೇಗ", re.I)


def summarize(text, kind, metadata=None):
    if metadata:
        if metadata.get("review_status") == "discarded":
            return {"gist": "Voice note discarded by sender", "tone": "Discarded"}
        if metadata.get("review_status") == "pending":
            return {"gist": "Voice transcript awaiting review", "tone": "Needs review"}
        if metadata.get("review_status") == "used":
            text = metadata.get("reviewed_text") or text
    line = " ".join((text or "").split())
    if not line:
        return {"gist": {"voice": "Voice note received", "media": "Attachment received"}.get(kind, "Awaiting a message"), "tone": "Unclassified"}
    if kind == "button":
        return {"gist": "Selected " + line[:65], "tone": "Response"}
    if DISPUTE.search(line):
        label, tone = "Disputed entry", "Needs review"
    elif URGENT.search(line):
        label, tone = "Time-sensitive request", "Urgent wording"
    else:
        label, tone = "", "Routine"
    excerpt = line.split("。")[0].split("।")[0]
    excerpt = excerpt if len(excerpt) <= 75 else excerpt[:72].rstrip() + "…"
    return {"gist": (label + " · " if label else "") + excerpt, "tone": tone}
