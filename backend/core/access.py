"""Who may do what. The agent proposes actions; this module decides if the speaker is allowed,
and whether the owner must approve first (human in the loop)."""
import db

ROLES = ["owner", "staff", "partner", "delivery", "supplier", "customer"]

ALLOWED = {
    "owner": {"*"},
    "staff": {"add_credit", "record_payment", "query_balance", "ask_people", "send_task", "set_reminder",
              "create_order", "restock", "correct_last", "undo_last", "send_document", "share_document",
              "mark_attendance", "announce", "update_price", "save_fact"},
    "partner": {"query_balance", "daily_summary"},
    "delivery": {"task_update"},
    "supplier": {"task_update"},
    "customer": {"query_own_balance", "promise", "dispute", "paid_claim", "create_order", "answer_question", "request_bill"},
}

# Tools that only read or talk back to the speaker; never need confirmation.
READ_ONLY = {"query_balance", "query_own_balance", "daily_summary", "request_bill"}


def can(role: str, tool: str) -> bool:
    allowed = ALLOWED.get(role or "customer", set())
    return "*" in allowed or tool in allowed


def needs_owner_approval(role: str, tool: str, args: dict) -> str | None:
    """Return a reason string if the owner must approve, else None."""
    if role == "owner":
        # The owner approves their own fan-outs and external documents via the preview step.
        if tool in ("ask_people", "send_task") and len(args.get("people", [])) > int(db.setting("fanout_approval") or 3):
            return "message to many people"
        if tool in ("send_document", "share_document", "announce"):
            return "document or announcement to other people"
        return None
    if tool in ("add_credit", "record_payment") and float(args.get("amount") or 0) >= float(db.setting("big_amount") or 2000):
        return "large amount by staff"
    if tool in ("ask_people", "send_task") and len(args.get("people", [])) > int(db.setting("fanout_approval") or 3):
        return "message to many people"
    if tool == "send_document":
        return "document to an outside party"
    return None
