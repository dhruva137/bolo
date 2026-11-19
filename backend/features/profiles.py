"""Business profiles: the owner says what the business is, Bolo configures itself.

A profile decides the words the bot uses (khata vs fees vs dues), what each role is called
(customer vs parent vs patient), which feature packs are on by default, and example phrases.
Every business gets the core; packs and add-ons can be toggled in the console.
"""
import json
import re

import db
from brain import llm

CORE = ["voice", "contacts", "dues", "broadcast", "tasks", "documents", "knowledge", "reminders", "summary", "watch"]

FEATURES = {
    # key: (label, description, core?)
    "voice": ("Voice understanding", "Any language, noise cleanup, two speech engines, Indian numbers & dates", True),
    "contacts": ("People & roles", "Who is who, what each role may do", True),
    "dues": ("Dues / khata / fees", "Credit, payments, balances with double verification and audio proof", True),
    "broadcast": ("Smart polls & announcements", "Ask many people, each in their language, with buttons and a live tally", True),
    "tasks": ("Tasks", "Send work to staff with Done/Later buttons and follow-ups", True),
    "documents": ("Documents & PDFs", "Bills, receipts, quotations, notices from your own templates", True),
    "knowledge": ("Knowledge base", "Your price list, timings, fee structure, forms: the bot answers and shares them", True),
    "reminders": ("Reminders", "Voice reminders for you and others", True),
    "summary": ("Daily summary", "A voice brief every night", True),
    "watch": ("Live watch & takeover", "See every chat live, pause the bot, reply yourself", True),
    "customer_loop": ("Customer confirmations", "Customers agree / dispute / promise to pay by voice", False),
    "upi_pay": ("UPI pay links", "Pay-now link with QR for any due", False),
    "orders": ("Orders", "Customers order by voice; you get an order ticket", False),
    "attendance": ("Attendance", "Mark who came by voice; monthly register", False),
    "restock": ("Restock / purchase orders", "Order from suppliers by voice", False),
    "calls": ("Phone-call escalation", "Call people who don't reply (Bolna)", False),
}

PROFILES = {
    "kirana": {
        "label": "Kirana / grocery shop", "dues_word": "udhaar",
        "roles": {"owner": "Owner", "staff": "Staff", "customer": "Customer", "delivery": "Delivery", "supplier": "Supplier", "partner": "Partner"},
        "packs": ["customer_loop", "upi_pay", "orders", "restock"],
        "hints": ["Ramesh chaar sau pachaas ka saman liya, Shanivar kodthane. Lakshmi 200 kotlu", "delivery team se pucho kaun aa raha hai",
                  "kaun kaun ka kitna baaki hai", "Balaji ko 10 sugar order karo"],
        "keywords": r"kirana|grocery|general store|provision|shop|dukaan|angadi|supermarket|store",
    },
    "school": {
        "label": "School / tuition", "dues_word": "fees",
        "roles": {"owner": "Principal", "staff": "Teacher", "customer": "Parent", "delivery": "Van driver", "supplier": "Vendor", "partner": "Trustee"},
        "packs": ["customer_loop", "upi_pay", "attendance"],
        "hints": ["Class 5 parents ko bolo kal school band hai", "Riya ki fees 4500 baaki, 10 tarikh tak",
                  "teachers se pucho Saturday PTM mein kaun aa raha hai", "aaj Aarav aur Meena absent the"],
        "keywords": r"school|tuition|coaching|class|students|teacher|academy|college|vidyalaya|shaale",
    },
    "clinic": {
        "label": "Clinic / diagnostic lab", "dues_word": "dues",
        "roles": {"owner": "Doctor", "staff": "Staff", "customer": "Patient", "delivery": "Sample collector", "supplier": "Supplier", "partner": "Partner"},
        "packs": ["customer_loop", "upi_pay"],
        "hints": ["kal ke saare patients ko yaad dilao 10 baje", "Mohan ka 800 baaki", "staff se pucho Sunday kaun aa raha hai"],
        "keywords": r"clinic|doctor|hospital|diagnostic|lab|pharmacy|medical|dental|physio",
    },
    "d2c": {
        "label": "Home business / D2C brand", "dues_word": "payment",
        "roles": {"owner": "Founder", "staff": "Team", "customer": "Customer", "delivery": "Courier", "supplier": "Supplier", "partner": "Reseller"},
        "packs": ["customer_loop", "upi_pay", "orders", "restock"],
        "hints": ["Priya ka order 3 jar pickle, 750 COD", "resellers ko naya price list bhejo", "Sharma ji ko invoice bhejo 20 jar 220 ke rate se"],
        "keywords": r"d2c|brand|pickle|home ?made|instagram|online|bakery|cake|tiffin|catering|boutique|tailor",
    },
    "distributor": {
        "label": "Distributor / wholesaler", "dues_word": "outstanding",
        "roles": {"owner": "Owner", "staff": "Salesman", "customer": "Retailer", "delivery": "Driver", "supplier": "Company", "partner": "Partner"},
        "packs": ["customer_loop", "upi_pay", "orders", "restock", "calls"],
        "hints": ["Ganesh Stores ka order 20 Parle-G 10 Maggi", "salesmen se pucho aaj kaun kaun beat pe hai", "kaun kaun ka outstanding hai"],
        "keywords": r"distribut|wholesale|stockist|dealer|agency|trader|fmcg|supply",
    },
    "contractor": {
        "label": "Contractor / site", "dues_word": "payment",
        "roles": {"owner": "Contractor", "staff": "Supervisor", "customer": "Client", "delivery": "Worker", "supplier": "Material supplier", "partner": "Partner"},
        "packs": ["attendance", "restock", "calls"],
        "hints": ["aaj site pe 12 log aaye, Ramu nahi aaya", "workers se pucho kal kaun aa raha hai", "cement 50 bag mangao"],
        "keywords": r"contract|construction|site|builder|mason|labour|interior|civil|electrician|plumb",
    },
    "society": {
        "label": "Housing society / association", "dues_word": "maintenance",
        "roles": {"owner": "Secretary", "staff": "Manager", "customer": "Resident", "delivery": "Security", "supplier": "Vendor", "partner": "Committee"},
        "packs": ["customer_loop", "upi_pay", "calls"],
        "hints": ["B-204 maintenance 2500 baaki", "sab residents se pucho Sunday meeting mein kaun aayega", "plumber ko bolo C block tank check karo"],
        "keywords": r"society|apartment|association|rwa|residents|flat|maintenance",
    },
    "generic": {
        "label": "Small business", "dues_word": "dues",
        "roles": {"owner": "Owner", "staff": "Staff", "customer": "Customer", "delivery": "Field staff", "supplier": "Supplier", "partner": "Partner"},
        "packs": ["customer_loop", "upi_pay"],
        "hints": ["Ramesh ka 500 baaki", "staff se pucho kal kaun aa raha hai", "aaj ka hisaab"],
        "keywords": r".",
    },
}


def classify(description: str) -> dict:
    """Description (any language) -> {type, name, summary}. LLM first, keywords as fallback."""
    out, _ = llm.json_call(
        "Classify a small Indian business from the owner's own description. Types: " + ", ".join(PROFILES) +
        '. Return JSON {"type": "...", "name": "<business name if said, else short descriptive name>", '
        '"summary": "<one line in English>", "languages": ["kn-IN", ...]}',
        description)
    if out and out.get("type") in PROFILES:
        return out
    low = description.lower()
    btype = next((k for k, p in PROFILES.items() if k != "generic" and re.search(p["keywords"], low)), "generic")
    m = re.search(r"(?:called|named|name is|naam|hesaru)\s+([A-Z][\w&' ]{2,40})", description)
    return {"type": btype, "name": (m.group(1).strip() if m else PROFILES[btype]["label"]), "summary": description[:140]}


def apply(description: str, name: str | None = None, btype: str | None = None) -> dict:
    info = classify(description) if not btype else {"type": btype, "name": name or PROFILES[btype]["label"], "summary": description[:140]}
    p = PROFILES[info["type"]]
    db.set_setting("business_type", info["type"])
    db.set_setting("shop_name", name or info.get("name") or p["label"])
    db.set_setting("business_desc", description)
    db.set_setting("features", json.dumps(CORE + p["packs"]))
    db.set_setting("onboarded", "1")
    db.audit("owner", "onboard", {"type": info["type"], "name": db.setting("shop_name")})
    return profile()


def profile() -> dict:
    btype = db.setting("business_type") or "generic"
    p = PROFILES.get(btype, PROFILES["generic"])
    return {"type": btype, "label": p["label"], "name": db.setting("shop_name"), "description": db.setting("business_desc"),
            "dues_word": p["dues_word"], "roles": p["roles"], "hints": p["hints"], "features": enabled(),
            "onboarded": db.setting("onboarded") == "1"}


def enabled() -> list[str]:
    try:
        return json.loads(db.setting("features") or "[]") or CORE
    except Exception:
        return CORE


def is_on(feature: str) -> bool:
    return feature in enabled()


def toggle(feature: str, on: bool) -> list[str]:
    feats = [f for f in enabled() if f != feature]
    if on or FEATURES.get(feature, ("", "", False))[2]:
        feats.append(feature)  # core features can't be switched off
    db.set_setting("features", json.dumps(feats))
    return feats


def role_label(role: str) -> str:
    return profile()["roles"].get(role, role.title())


# Which feature a tool needs (tools not listed are always available).
TOOL_FEATURE = {
    "add_credit": "dues", "record_payment": "dues", "query_balance": "dues", "query_own_balance": "dues",
    "promise": "customer_loop", "dispute": "customer_loop", "paid_claim": "dues",
    "ask_people": "broadcast", "announce": "broadcast", "send_task": "tasks", "send_document": "documents",
    "share_document": "knowledge", "answer_question": "knowledge", "set_reminder": "reminders",
    "daily_summary": "summary", "create_order": "orders", "restock": "restock", "mark_attendance": "attendance",
}
