"""Turn what someone said into a list of tool calls.

Primary: an LLM with a strict JSON contract and the shop's own context (contacts, products,
roles). Fallback: deterministic rules that cover the core shop phrases in Hindi, Kannada and
English, so the bot still works with no API keys (and so we have a baseline to evaluate against).
"""
import datetime as dt
import re

import db
from brain import llm
from brain.normalize import parse_date, words_to_numbers
from core import contacts as C
from features import knowledge, profiles

OWNER_TOOLS = """
add_credit(name, amount, items?, due?)          customer took goods on credit (udhaar / khata / "saman liya")
record_payment(name, amount, mode?)             customer paid back (diye / kotlu / jama / paid)
query_balance(name?)                            how much someone (or everyone) owes
ask_people(question, people[], options?, when?) ask several people something and collect answers (who is coming? yes/no)
send_task(people[], task, when?)                tell staff / delivery team to do something
set_reminder(text, when, name?)                 remind the speaker (or a person) later
send_document(kind, to, items[{name,qty,rate}], note?)  kind = bill | quotation | purchase_order | statement
restock(items[{name, qty}])                     order stock from the supplier
share_document(title, people[])                 send a saved file from the knowledge base (fee structure, price list, form)
announce(message, people[])                     one-way announcement to people or groups ("parents ko bolo kal chutti hai")
mark_attendance(people[], status, date?)        who came / who was absent today
save_rule(rule)                                 the owner teaches a rule or policy to follow from now on ("ab se…", "hamesha…", "rule hai…")
correct_last(amount?, name?)                    fix the previous entry ("nahi, 540")
undo_last()                                     remove the previous entry ("galat tha, hatao")
daily_summary()                                 today's totals
update_price(items[{name, price, unit?}], notify?)  notify=true if the owner also says to tell customers. The owner changes a price in the shop's list ("aaj tomato 40 ka kilo", "atta ab 290", "tomato ka rate 40 kar do")
save_fact(text)                                 shop info customers may ask about: timings, holiday, delivery charge, stock ("kal dukaan 2 baje band", "delivery free above 300")
"""
CUSTOMER_TOOLS = """
query_own_balance()                 how much do I owe
promise(when, amount?)              I will pay on <day>
dispute(amount?, reason?)           the entry is wrong / I didn't take that
paid_claim(amount?, mode?)          I already paid (cash / GPay / PhonePe)
create_order(items[{name, qty}])    I want to buy these
request_bill()                      send me my bill / statement / hisaab so I can pay
answer_question(question)           any other question (timings, prices, fees, availability)
"""

GROUPS = {"delivery team": "delivery", "delivery boys": "delivery", "delivery": "delivery", "staff": "staff",
          "partners": "partner", "partner": "partner", "suppliers": "supplier", "supplier": "supplier",
          "teachers": "staff", "teacher": "staff", "parents": "customer", "parent": "customer", "residents": "customer",
          "customers": "customer", "patients": "customer", "retailers": "customer", "resellers": "partner",
          "salesmen": "staff", "workers": "delivery", "drivers": "delivery", "sab": "customer", "everyone": "customer"}


def _context(role: str) -> str:
    people = [f"{c['name']} ({c['role']}{', aka ' + '/'.join(c['aliases']) if c['aliases'] else ''})"
              for c in C.all_contacts()]
    products = [r["name"] for r in db.q("SELECT name FROM catalog ORDER BY name LIMIT 60")]
    today = dt.date.today()
    prof = profiles.profile()
    docs = [k["title"] for k in knowledge.all_items() if k["kind"] == "file"]
    rules = [k["text"] for k in knowledge.all_items() if k["title"] == "Rule"][:15]
    roles = ", ".join(f"{k}={v}" for k, v in prof["roles"].items())
    return (f"Today: {today.isoformat()} ({today.strftime('%A')}). Business: {prof['name']} ({prof['label']}). "
            f"{(prof['description'] or '')[:300]}\nRole names: {roles}. Money owed is called '{prof['dues_word']}'.\n"
            f"Enabled features: {', '.join(prof['features'])}.\nKnowledge-base files: {', '.join(docs) or 'none'}.\n"
            f"Owner's rules to follow: {' | '.join(rules) or 'none'}.\n"
            f"Speaker role: {role}.\nKnown people: {'; '.join(people) or 'none'}.\n"
            f"Products: {', '.join(products) or 'none'}.\n"
            "Groups you may use in people[]: @delivery, @staff, @partner, @supplier, @customer.")


def _system(role: str) -> str:
    tools = CUSTOMER_TOOLS if role == "customer" else OWNER_TOOLS
    return (
        "You are Bolo, the bookkeeper and operations assistant of a small Indian shop. People speak to you in "
        "voice notes in any Indian language, often mixing languages. You receive the transcript (and sometimes a "
        "second transcript from another speech engine). Convert it into tool calls.\n"
        f"TOOLS:\n{tools}\n"
        "RULES: One voice note can contain several actions; return all of them in order. Copy names exactly as "
        "spoken (romanized). Amounts are numbers in rupees; if two transcripts disagree on a number, use the first "
        "and add \"amount_alt\" with the other. Keep 'when'/'due' as spoken (e.g. 'Shanivar', 'kal 5 baje'). "
        "Never invent amounts or people. If nothing matches, return an empty list.\n"
        'Return ONLY JSON: {"actions": [{"tool": "...", "args": {...}}], "language": "<bcp47 like kn-IN>"}'
    )


# "tomato ka rate ab 40", or a transcript in mixed script: "Tomato का rate अब 40 हो गया"
PRICE_RE = re.compile(r"([a-zऀ-ॿ][a-zऀ-ॿ\- ]{1,30}?)\s+(?:ka|ki|ke|का|की|के)?\s*"
                      r"(?:rate|price|bhav|bhaav|daam|keemat|रेट|भाव|दाम|कीमत)\s*(?:ab|aaj|अब|आज)?\s*(\d+(?:\.\d+)?)")


def plan(text: str, role: str, text_b: str = "") -> tuple[list[dict], str]:
    if role != "customer" and PRICE_RE.search(text.lower()):
        return rule_plan(text, role), "rules"  # a price change: never let the LLM read it as udhaar
    if role != "customer" and re.match(r"\s*(yaad rakh|yaad rakhna|note kar|customers? ko bata(na|o)? ki)\b", text.lower()):
        return rule_plan(text, role), "rules"  # a shop fact for customers, not a reminder
    user = f"{_context(role)}\nTRANSCRIPT A: {text}\n" + (f"TRANSCRIPT B: {text_b}\n" if text_b else "")
    out, provider = llm.json_call(_system(role), user)
    if isinstance(out, dict) and isinstance(out.get("actions"), list):
        if all(isinstance(a, dict) and isinstance(a.get("tool"), str)
               and isinstance(a.get("args", {}), dict) for a in out["actions"]):
            actions = out["actions"]
            if any(a["tool"] == "update_price" for a in actions):
                if any(a["tool"] == "announce" for a in actions):
                    for a in actions:
                        if a["tool"] == "update_price":
                            a.setdefault("args", {})["notify"] = True
                actions = [a for a in actions if a["tool"] != "announce"]
            if actions:
                return actions, provider
            fallback = rule_plan(text, role)
            if fallback and not all(a["tool"] == "answer_question" for a in fallback):
                return fallback, "rules"
            return [], provider
    return rule_plan(text, role), "rules"


# ---------------------------------------------------------------- offline rule planner
KW = {
    "undo": r"\b(galat tha|hatao|cancel|delete|undo|tegedu haaku|beda)\b",
    "correct": r"^(nahi|nahin|illa|no|alla)\b[ ,]*",
    "summary": r"(aaj ka hisaab|aaj ka hisab|summary|ivattina lekka|today.?s total)",
    "balance": r"(kitna baaki|kitna baki|baaki kitna|balance|kitne paise|eshtu baaki|kaun kaun|who owes|कितना बाकी|बाकी कितना|बकाया कितना|ಬಾಕಿ ಎಷ್ಟು|ಎಷ್ಟು ಬಾಕಿ)",
    "ask": r"(kaun aa raha|kaun aayega|pucho|poocho|\bask\b|yes or no|haan ya na|barthira|barteera|kelu)",
    "task": r"(ko bolo|ko batao|\btell\b|heli|ko kaho)",
    "doc": r"(quotation|\bbill\b|invoice|challan|estimate|statement|purchase order)",
    "restock": r"(mangao|mangwao|order karo|beku|khatam|chahiye|restock|tarisu)",
    "remind": r"(yaad dila|remind|nenapisu)",
    "rule": r"^(ab se|aaj se|hamesha|rule|niyam|from now|always|inmunde|yaavaagalu)\b",
    "attendance": r"(absent|present|nahi aaya|nahi aayi|nahi aaye|chutti|attendance|haajar|gairu|bandilla|aaye the|aaye hain)",
    "share": r"(bhejo|send|kalisi|share)",
    "announce": r"(ko bolo|ko batao|announce|sabko bolo|inform)",
    "payment": r"\b(diye|diya|de diya|kotlu|kotta|kottalu|kottaru|kottidare|paid|jama|wapas|vaapas)\b"
               r"|दिए|दिये|दिया|चुकाए|चुकाया|जमा|वापस|भुगतान|ಕೊಟ್ಟ|ಕಟ್ಟಿದ|ಮರುಪಾವತಿ|ಪಾವತಿಸಿದ|ಜಮಾ",
    "credit": r"(udhaar|udhar|saman|liya|le gaya|khata|khate|credit|likh|tegedukond|thagondu)",
}
CUST = {
    "promise": r"(dunga|dungi|de dunga|de dungi|kodthini|kodtini|kodtene|pay karunga|pay karungi|will pay|tharthini|दूंगा|दूँगा|दूँगी|दूंगी|ಕೊಡುತ್ತೇನೆ|ಕೊಡ್ತೀನಿ)",
    "dispute": r"(galat|wrong|tappu|nahi liya|maine nahi|did not|not mine|गलत|ग़लत|नहीं लिया|ತಪ್ಪು|ತೆಗೆದುಕೊಂಡಿಲ್ಲ)",
    "paid": r"(de diya|diya hai|paid|gpay|phonepe|paytm|kar diya|kottidini|kottidene|दे दिया|दिए|जमा किए|चुका दिया|ಕೊಟ್ಟಿದ್ದೇನೆ|ಕಟ್ಟಿದ್ದೇನೆ|ಪಾವತಿಸಿದ್ದೇನೆ)",
    "balance": r"(kitna|baaki|balance|eshtu|how much|बाकी|बकाया|ಬಾಕಿ)",
}
STOP = {"ne", "ko", "ka", "ki", "ke", "rupay", "rupees", "rs", "saman", "aur", "and", "mattu", "ka", "kilo", "kg"}
NUM_RE = r"\d+(?:\.\d+)?"


def _names_in(text: str) -> list[str]:
    found: list[str] = []
    words = re.findall(r"[^\s,.;]+", text)
    for i in range(len(words)):
        for span in (2, 1):
            phrase = " ".join(words[i:i + span])
            if len(C.romanize(phrase)) < 3:
                continue
            cands = C.find(phrase)
            if cands and cands[0]["score"] >= 85 and cands[0]["contact"]["name"] not in found:
                found.append(cands[0]["contact"]["name"])
                break
    return found


def _first_name_token(clause: str) -> str:
    for w in re.findall(r"[A-Za-zऀ-ൿ]+", clause):
        if parse_date(w):
            continue
        r = C.romanize(w)
        if len(r) >= 3 and r not in STOP and not any(re.search(p, w.lower()) for p in KW.values()):
            return w
    return ""


def _group_people(text: str) -> list[str]:
    low = text.lower()
    for k, g in GROUPS.items():
        if re.search(rf"\b{k}\b", low):
            return [f"@{g}"]
    return []


def _whole_note_intent(norm: str) -> list[dict] | None:
    """Polls, tasks, documents and reminders span the whole note; don't split them."""
    low = norm.lower()
    names = _names_in(norm)
    people = names or _group_people(norm)
    if re.search(KW["ask"], low):
        return [{"tool": "ask_people", "args": {"question": norm, "people": people, "when": norm}}]
    if profiles.is_on("attendance") and re.search(KW["attendance"], low) and names:
        status = "absent" if re.search(r"absent|nahi|chutti|gairu|bandilla", low) else "present"
        return [{"tool": "mark_attendance", "args": {"people": names, "status": status, "date": norm}}]
    if re.search(KW["share"], low):
        hits = knowledge.find(norm, kind="file")
        if hits and hits[0]["score"] >= 60:
            return [{"tool": "share_document", "args": {"title": hits[0]["title"], "people": people}}]
    if re.search(KW["task"], low) and people and re.search(r"karo|kar do|check|lao|le aao|maadi|do it|clean|deliver", low):
        return [{"tool": "send_task", "args": {"task": norm, "people": people}}]
    if re.search(KW["announce"], low) and people:
        return [{"tool": "announce", "args": {"message": norm, "people": people}}]
    # "Lakshmi ka hisaab bhejo" / "Ramesh ko khata bhejo" = send that customer their statement.
    if names and re.search(r"(hisaab|hisab|khata|lekka).*(bhej|send|kalis)", low):
        return [{"tool": "send_document", "args": {"kind": "statement", "to": names[0], "items": [], "note": norm}}]
    if re.search(KW["doc"], low):
        kind = next((k for k in ("quotation", "purchase_order", "statement", "bill") if k.split("_")[0] in low), "bill")
        items = []
        m = re.search(r"(\d+)\s*(?:bag|bags|kg|kilo|packet|packets|piece|pcs)?\s+([a-z ]+?)\s+(\d+)\s*(?:ke rate|rate|rupees|rs|each)", low)
        if m:
            items = [{"name": m.group(2).strip(), "qty": float(m.group(1)), "rate": float(m.group(3))}]
        return [{"tool": "send_document", "args": {"kind": kind, "to": names[0] if names else "", "items": items, "note": norm}}]
    if re.search(KW["remind"], low):
        return [{"tool": "set_reminder", "args": {"text": norm, "when": norm, "name": names[0] if names else ""}}]
    if re.search(KW["summary"], low):
        return [{"tool": "daily_summary", "args": {}}]
    return None


def _order_items(text: str) -> list[dict]:
    """'please send 1 fortune oil and 2 parle-g' -> [{name: fortune oil, qty: 1}, {name: parle-g, qty: 2}]"""
    filler = r"\b(please|pls|send|me|bhejo|bhej do|bhej|de do|dena|chahiye|order|i want|want|bhaiya|anna|can you|ka|ki|ke)\b"
    items = []
    for part in re.split(r"\s+(?:and|aur|mattu|&)\s+|,", text.lower()):
        part = words_to_numbers(part)[0]  # "do packet" -> "2 packet", "ek" -> "1"
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilo|packets?|pack|bottles?|litre|ltr)?\s+(.+)", part)
        qty = float(m.group(1)) if m else 1.0
        name = re.sub(filler, " ", m.group(2) if m else part)
        name = re.sub(r"(\s+\d+(?:\.\d+)?)+\s*$", "", name)  # "bhej do" became "bhej 2"
        name = re.sub(r"\s+", " ", name).strip(" .")
        if name:
            items.append({"name": name, "qty": qty})
    return items or [{"name": text, "qty": 1}]


def _customer_actions(clauses: list[str]) -> list[dict]:
    actions = []
    for cl in clauses:
        low = cl.lower()
        nums = [float(n) for n in re.findall(NUM_RE, cl)]
        amount = nums[-1] if nums else None
        if re.search(r"\b(bill|statement|invoice|receipt)\b|hisaab bhej|hisab bhej|khata bhej", low):
            actions.append({"tool": "request_bill", "args": {}})
        elif re.search(CUST["promise"], low):
            actions.append({"tool": "promise", "args": {"when": cl, "amount": amount}})
        elif re.search(CUST["dispute"], low):
            actions.append({"tool": "dispute", "args": {"amount": amount, "reason": cl}})
        elif re.search(CUST["paid"], low):
            actions.append({"tool": "paid_claim", "args": {"amount": amount}})
        elif re.search(CUST["balance"], low) and not re.search(r"kab|when|timing|price|rate|kitne ka", low):
            actions.append({"tool": "query_own_balance", "args": {}})
        elif profiles.is_on("orders") and re.search(r"bhejo|chahiye|order|kilo|kg|packet|beku|send|de do|jar|bottle", low):
            actions.append({"tool": "create_order", "args": {"items": _order_items(cl)}})
        else:
            actions.append({"tool": "answer_question", "args": {"question": cl}})
    return actions


def rule_plan(text: str, role: str) -> list[dict]:
    norm, _ = words_to_numbers(text)
    clauses = [c.strip() for c in re.split(r"\.(?!\d)|[;।\n]|,(?!\d)|\s+(?:aur|and|mattu|matte|और|ಮತ್ತು)\s+", norm) if c and c.strip()]
    if role == "customer":
        return _customer_actions([norm])  # a customer's note is one intent: "galat hai, 350 tha"
    low_all = norm.lower().strip()
    nums_all = [float(n) for n in re.findall(NUM_RE, norm)]
    if re.search(KW["correct"], low_all) and nums_all and not _names_in(norm):
        return [{"tool": "correct_last", "args": {"amount": nums_all[-1]}}]  # "nahi, 540"
    if re.search(KW["rule"], low_all):
        return [{"tool": "save_rule", "args": {"rule": text.strip()}}]
    if re.search(r"^(yaad rakh|yaad rakhna|note kar|customers? ko bata(na|o)? ki)", low_all):
        return [{"tool": "save_fact", "args": {"text": re.sub(r"^(yaad rakhna|yaad rakh|note kar|customers? ko bata(na|o)? ki)\s*[:,\-]?\s*", "", norm, flags=re.I).strip(" :,-")}}]
    m = PRICE_RE.search(low_all)
    if m:
        return [{"tool": "update_price", "args": {"items": [{"name": m.group(1).strip(), "price": float(m.group(2))}]}}]
    whole = _whole_note_intent(norm)
    if whole:
        return whole
    actions: list[dict] = []
    for cl in clauses:
        low = cl.lower()
        nums = [float(n) for n in re.findall(NUM_RE, cl)]
        amount = nums[-1] if nums else None
        names = _names_in(cl)
        # "Shanivar dega" right after a credit is that credit's due date
        if parse_date(cl) and not names and amount is None and actions and actions[-1]["tool"] == "add_credit":
            actions[-1]["args"]["due"] = cl
            continue
        if re.search(KW["correct"], low) and amount is not None and not names:
            actions.append({"tool": "correct_last", "args": {"amount": amount}})
        elif re.search(KW["undo"], low):
            actions.append({"tool": "undo_last", "args": {}})
        elif re.search(KW["restock"], low) and not names:
            item = re.sub(NUM_RE + r"|kilo|kg|beku|chahiye|mangao|mangwao|order karo|khatam|ho raha hai", "", low).strip()
            actions.append({"tool": "restock", "args": {"items": [{"name": item, "qty": amount or 1}]}})
        elif re.search(KW["balance"], low):
            actions.append({"tool": "query_balance", "args": {"name": names[0] if names else ""}})
        elif amount is not None and (names or _first_name_token(cl)):
            name = names[0] if names else _first_name_token(cl)
            tool = "record_payment" if re.search(KW["payment"], low) else "add_credit"
            args: dict = {"name": name, "amount": amount}
            if tool == "add_credit" and parse_date(cl):
                args["due"] = cl
            actions.append({"tool": tool, "args": args})
    return actions
