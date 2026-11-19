"""End-to-end flow test in offline mode (no API keys, simulator instead of WhatsApp).

Run from backend/:  python -m tests.test_flow
Uses a temporary data directory, so it never touches your real database.
"""
import os
import json
import sys
import tempfile
from unittest.mock import patch

os.environ["BOLO_DATA_DIR"] = tempfile.mkdtemp(prefix="bolo_test_")
for k in ("SARVAM_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "WA_TOKEN", "WA_PHONE_NUMBER_ID", "BOLNA_API_KEY",
          "TWILIO_SID", "TWILIO_TOKEN", "BOLNA_AGENT_ID"):
    os.environ[k] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import app as bolo  # noqa: E402

OWNER, RAMESH, LAKSHMI, RAVI, IMRAN, KIRAN = ("919900000001", "919900000011", "919900000013",
                                              "919900000003", "919900000004", "919900000002")
failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def last_out(client, phone, n=1):
    msgs = [m for m in client.get("/api/messages", params={"phone": phone}).json() if m["direction"] == "out"]
    return msgs[-n:] if n > 1 else (msgs[-1] if msgs else {})


def say(client, phone, text=None, button=None):
    r = client.post("/api/simulate", json={"phone": phone, **({"button": button} if button else {"text": text})})
    assert r.status_code == 200, r.text


with TestClient(bolo.app) as client:
    client.post("/api/seed")
    client.put("/api/settings", json={"voice_replies": "0", "upi_id": "lakshmistores@upi"})

    # 1. owner: several entries in one note, Hinglish + Kannada, spoken numbers
    say(client, OWNER, "Ramesh chaar sau pachaas ka saman liya, Shanivar kodthane. Lakshmi 200 kotlu")
    card = last_out(client, OWNER)
    check("multi-action card", "①" in card.get("text", "") and "②" in card.get("text", ""), card.get("text"))
    check("two Rameshes -> pick buttons", any(b[0].startswith("pick:") for b in card.get("buttons", [])), card.get("buttons"))
    pick = next(b[0] for b in card["buttons"] if b[0].startswith("pick:") and "milk" in b[1].lower())
    say(client, OWNER, button=pick)
    card2 = last_out(client, OWNER)
    ok = next((b[0] for b in card2.get("buttons", []) if b[0].startswith("ok:")), None)
    check("after pick -> confirm buttons", ok is not None, card2.get("buttons"))
    check("amount read back in words", "chaar sau pachaas" in card2.get("text", ""), card2.get("text"))
    say(client, OWNER, button=ok)
    led = client.get("/api/ledger").json()
    ramesh = next(b for b in led["balances"] if b["phone"] == RAMESH)
    lakshmi = next(b for b in led["balances"] if b["phone"] == LAKSHMI)
    check("Ramesh +450", ramesh["balance"] == 450, ramesh)
    check("Lakshmi 450-200=250", lakshmi["balance"] == 250, lakshmi)
    check("due date captured", any(e["due_date"] for e in led["entries"] if e["contact_id"] == ramesh["id"]))

    # 2. customer loop: statement with agree/dispute/pay, then a voice-style dispute
    stmt = next((m for m in client.get("/api/messages", params={"phone": RAMESH}).json()
                 if m["direction"] == "out" and m["buttons"]), {})
    check("customer statement sent", "udhaar" in stmt.get("text", "") and len(stmt.get("buttons", [])) == 3, stmt)
    original_id = int(stmt["buttons"][0][0].split(":")[1])
    original = bolo.db.q1("SELECT * FROM ledger WHERE id=?", (original_id,))
    say(client, RAMESH, "haan")
    check("natural agreement linked to statement", bolo.ledger.get(original_id)["status"] == "agreed")
    say(client, RAMESH, "galat hai, 350 tha")
    owner_msg = last_out(client, OWNER)
    check("dispute reaches owner with keep/change", any(b[0].startswith("change:") for b in owner_msg.get("buttons", [])), owner_msg)
    change = next(b[0] for b in owner_msg["buttons"] if b[0].startswith("change:"))
    say(client, RAMESH, button=change)
    check("only owner resolves dispute", bolo.ledger.balance(ramesh["id"]) == 450)
    say(client, OWNER, button=change)
    say(client, OWNER, button=change)
    ramesh = next(b for b in client.get("/api/ledger").json()["balances"] if b["phone"] == RAMESH)
    check("dispute resolved to 350", ramesh["balance"] == 350, ramesh)
    check("original ledger row immutable", original == bolo.db.q1("SELECT * FROM ledger WHERE id=?", (original_id,)))
    entries = client.get("/api/ledger").json()["entries"]
    check("ledger API overlays status", next(e for e in entries if e["id"] == original_id)["status"] == "disputed")

    # 3. customer promise + balance query + paid claim
    say(client, RAMESH, "Saturday dunga")
    check("promise noted", "Noted" in last_out(client, RAMESH).get("text", ""))
    say(client, RAMESH, "kitna baaki hai?")
    check("own balance", "350" in last_out(client, RAMESH).get("text", ""), last_out(client, RAMESH))
    say(client, RAMESH, "maine 100 gpay kar diya")
    owner_msg = last_out(client, OWNER)
    recv = next((b[0] for b in owner_msg.get("buttons", []) if b[0].startswith("recv:")), None)
    check("paid claim asks owner", recv is not None, owner_msg)
    say(client, OWNER, button=recv)
    ramesh = next(b for b in client.get("/api/ledger").json()["balances"] if b["phone"] == RAMESH)
    check("payment confirmed -> 250", ramesh["balance"] == 250, ramesh)
    say(client, RAMESH, "maine gpay kar diya")
    check("missing payment amount asks for a value", "Kitna pay kiya" in last_out(client, RAMESH)["text"])
    say(client, RAMESH, "maine 150 gpay kar diya")
    declined = next(b[0] for b in last_out(client, OWNER)["buttons"] if b[0].startswith("norecv:"))
    say(client, RAMESH, button=declined)
    claim_id = int(declined.split(":")[1])
    check("payment decisions require owner", bolo.ledger.get(claim_id)["status"] == "claimed")
    say(client, OWNER, button=declined)
    say(client, OWNER, button=f"recv:{claim_id}")
    check("rejected payment stays outside balance", bolo.ledger.get(claim_id)["status"] == "rejected"
          and bolo.ledger.balance(ramesh["id"]) == 250)

    # 4. correction after commit: "nahi, 540"
    say(client, OWNER, "Fatima 450 udhaar")
    c = last_out(client, OWNER)
    say(client, OWNER, button=next(b[0] for b in c["buttons"] if b[0].startswith("ok:")))
    say(client, OWNER, "nahi, 540")
    fatima = next(b for b in client.get("/api/ledger").json()["balances"] if b["name"] == "Fatima")
    check("correction 450->540 (320 opening + 540)", fatima["balance"] == 860, fatima)
    check("chain still valid after corrections", client.get("/api/ledger").json()["verify"]["ok"])

    # 5. smart poll: "kaun aa raha hai" -> delivery team gets buttons, owner gets tally
    say(client, OWNER, "Saturday 5 baje stock count hai, delivery team se pucho kaun aa raha hai")
    ravi_msg = last_out(client, RAVI)
    check("poll reached Ravi with buttons", any(b[0].startswith("poll:") for b in ravi_msg.get("buttons", [])), ravi_msg)
    poll_id = ravi_msg["buttons"][0][0].split(":")[1]
    say(client, RAVI, button=f"poll:{poll_id}:99")
    say(client, RAMESH, button=f"poll:{poll_id}:0")
    check("poll counts only valid choices by invitees", client.get("/api/polls").json()[0]["answered"] == 0)
    say(client, RAVI, button=next(b[0] for b in ravi_msg["buttons"] if b[0].endswith(":0")))
    imran_msg = last_out(client, IMRAN)
    say(client, IMRAN, button=next(b[0] for b in imran_msg["buttons"] if b[0].endswith(":1")))
    tally = last_out(client, OWNER)
    check("owner gets full tally", "2/2" in tally.get("text", ""), tally)

    # 6. staff permissions: staff can add credit, partner cannot
    say(client, "919900000006", "Selvi 300 udhaar")
    check("partner blocked from credit", "permission" in last_out(client, "919900000006").get("text", ""))

    # 7. document with owner approval
    say(client, OWNER, "Balaji ko quotation bhejo, 50 bag cement 380 ke rate se")
    appr = last_out(client, OWNER)
    approve = next((b[0] for b in appr.get("buttons", []) if b[0].startswith("approve:")), None)
    check("document needs approval", approve is not None, appr)
    say(client, OWNER, button=approve)
    sup = last_out(client, "919900000007")
    check("supplier received document", sup.get("kind") == "document" and sup.get("media"), sup)
    pdf = client.get(sup["media"])
    check("supplier gets downloadable PDF bytes", pdf.status_code == 200 and pdf.content.startswith(b"%PDF-"))
    quote = bolo.db.q1("SELECT fields FROM documents WHERE template='quotation'")
    check("quotation captures 50 bags at 380", "'qty': 50.0" in quote["fields"] and "'rate': 380.0" in quote["fields"])

    # 8. balance query + summary
    say(client, OWNER, "kaun kaun ka kitna baaki hai")
    check("balance overview", "Total baaki" in last_out(client, OWNER).get("text", ""))
    say(client, OWNER, "aaj ka hisaab")
    check("summary", "Aaj ka hisaab" in last_out(client, OWNER).get("text", ""))

    # 9. watch mode: bot paused -> messages recorded, no reply; human takeover reply
    client.post("/api/live/mode", json={"paused": True})
    n_before = len(client.get("/api/messages", params={"phone": OWNER}).json())
    say(client, OWNER, "Selvi 100 udhaar")
    after = client.get("/api/messages", params={"phone": OWNER}).json()
    check("paused: recorded, no reply", len(after) == n_before + 1 and after[-1]["direction"] == "in", after[-1])
    client.post("/api/live/mode", json={"paused": False})
    client.post("/api/live/reply", json={"phone": RAMESH, "text": "Namaste, owner here"})
    check("human reply stored", last_out(client, RAMESH).get("meta", {}).get("human") is True)
    check("live threads list", len(client.get("/api/live/threads").json()["threads"]) >= 3)

    # 10. knowledge: customer question answered from facts (offline)
    say(client, RAMESH, "dukaan kab tak khula hai? timing kya hai")
    check("question answered from knowledge", "10 pm" in last_out(client, RAMESH).get("text", ""), last_out(client, RAMESH))

    # 10b. teach a rule by voice; numbered reply answers buttons
    say(client, OWNER, "Ab se 1000 se upar udhaar dene se pehle mujhse confirm karna")
    preview = last_out(client, OWNER)
    check("rule preview explains credit threshold", "Credit above ₹1,000" in preview["text"])
    today, ongoing, cancel = [b[0] for b in preview["buttons"]]
    say(client, KIRAN, button=today)
    check("only owner can approve preview", not bolo.knowledge.credit_needs_owner(1001))
    say(client, OWNER, button=today)
    say(client, OWNER, button=ongoing)
    rules = [row for row in bolo.knowledge.all_items() if row["title"] == "Rule"]
    check("today rule saved once", len(rules) == 1 and bolo.knowledge.credit_needs_owner(1001)
          and not bolo.knowledge.credit_needs_owner(1000))
    expires = rules[0]["expires_at"]
    check("expiry is IST midnight", (expires + 19800) % 86400 == 0)
    with patch.object(bolo.db, "now", return_value=expires):
        check("expired rule leaves planner and knowledge", not bolo.knowledge.credit_needs_owner(1001)
              and rules[0]["text"] not in bolo.agent.planner._context("owner")
              and rules[0]["text"] not in bolo.knowledge.context_for_llm())
    say(client, OWNER, "Always confirm credit above 25")
    cancel = last_out(client, OWNER)["buttons"][2][0]
    say(client, OWNER, button=cancel)
    say(client, OWNER, button=cancel.replace("cancel", "ongoing"))
    check("cancelled rule cannot be revived", not bolo.knowledge.credit_needs_owner(26))
    say(client, OWNER, "Always approve credit above 2000")
    say(client, OWNER, button=last_out(client, OWNER)["buttons"][1][0])
    with patch.object(bolo.db, "now", return_value=expires + 86400):
        check("ongoing rule survives midnight", bolo.knowledge.credit_needs_owner(2001))
    say(client, KIRAN, "Selvi 1100 udhaar")
    say(client, KIRAN, button=last_out(client, KIRAN)["buttons"][0][0])
    check("staff credit waits for owner under taught rule", any(b[0].startswith("approve:") for b in last_out(client, OWNER)["buttons"]))
    say(client, OWNER, "Selvi 120 udhaar")
    say(client, OWNER, "1")
    check("numbered reply confirms", "Likh liya" in last_out(client, OWNER).get("text", ""), last_out(client, OWNER))

    # 11. unknown sender becomes an opted-in customer; nonsense gets a helpful reply
    say(client, "919811112222", "hello")
    check("new contact created", any(c["phone"] == "919811112222" for c in client.get("/api/contacts").json()))

    # Each registered tool must be reachable from a real utterance through the simulator.
    # Check the stored plan as well as observable effects, since the endpoint always returns ok.
    say(client, OWNER, "undo")
    check("undo reverses latest entry", "Hata diya" in last_out(client, OWNER)["text"])
    say(client, OWNER, "delivery team ko bolo deliver karo")
    check("task reaches crew", "Kaam" in last_out(client, RAVI)["text"])
    say(client, OWNER, "remind me tomorrow 5 pm")
    check("reminder scheduled", "Yaad dila" in last_out(client, OWNER)["text"])
    say(client, OWNER, "sugar 10 kg mangao")
    check("restock drafts purchase order", "Purchase order" in last_out(client, OWNER)["text"])
    say(client, OWNER, "staff ko bolo kal band hai")
    check("announcement waits for approval", "Announce" in last_out(client, OWNER)["text"])
    say(client, OWNER, button=last_out(client, OWNER)["buttons"][0][0])
    check("approved announcement reaches staff", "kal band" in last_out(client, KIRAN)["text"])
    client.post("/api/knowledge/file", data={"title": "Price list"}, files={"file": ("prices.txt", b"Sugar 46", "text/plain")})
    say(client, OWNER, "staff ko Price list bhejo")
    check("saved file waits for approval", "Price list" in last_out(client, OWNER)["text"])
    say(client, OWNER, button=last_out(client, OWNER)["buttons"][0][0])
    check("approved knowledge file arrives", last_out(client, KIRAN)["kind"] == "document")
    client.put("/api/features/attendance", json={"on": True})
    say(client, OWNER, "Ravi absent")
    check("attendance saved", any(r["name"] == "Ravi" and r["status"] == "absent" for r in client.get("/api/attendance").json()))
    say(client, OWNER, "tomato ka rate 40 kar do")
    check("owner updates a price by voice", any(r["price"] == 40 for r in client.get("/api/catalog").json() if "tomato" in r["name"].lower()))
    say(client, OWNER, "yaad rakh: 300 se upar delivery free hai")
    check("owner saves a shop fact by voice", any("delivery" in (k.get("text") or "") for k in client.get("/api/knowledge").json()))
    say(client, RAMESH, "mera bill bhejo, payment karna hai")
    check("customer gets their own bill as a PDF", any(m["kind"] == "document" for m in client.get(f"/api/messages?phone={RAMESH}").json()))
    say(client, RAMESH, "send me 2 kilo atta")
    card = last_out(client, RAMESH)
    check("customer order is priced and asks to confirm", any(b[0].endswith(":ok") and b[0].startswith("ord:") for b in card["buttons"]))
    say(client, RAMESH, button=card["buttons"][0][0])
    check("customer order reaches owner", "New order" in last_out(client, OWNER)["text"] and "Ramesh" in last_out(client, OWNER)["text"])
    exercised = {action["tool"] for event in bolo.db.q("SELECT plan FROM events WHERE plan IS NOT NULL")
                 for action in json.loads(event["plan"])["actions"]}
    expected = set(bolo.agent.TOOLS) | bolo.agent.MONEY_TOOLS
    check(f"all {len(expected)} tools reached through POST /api/simulate", expected <= exercised, sorted(expected - exercised))

    # Risky mode commits only unambiguous, low-value entries.
    client.put("/api/settings", json={"confirm_money": "risky"})
    for amount in (50, 501):
        before = len(bolo.ledger.effective())
        say(client, OWNER, f"Selvi {amount} udhaar")
        card = last_out(client, OWNER)
        check(f"risk guard reads back {amount}", len(bolo.ledger.effective()) == before
              and any(b[0].startswith("ok:") for b in card["buttons"]))
        say(client, OWNER, button=next(b[0] for b in card["buttons"] if b[0].startswith("redo:")))
    say(client, OWNER, "Lakshmi 101.25 udhaar")
    check("decimal rupee amount preserved", bolo.ledger.effective()[-1]["amount"] == 101.25)
    for phrase, name in (("रमेश कुमार ने ३९ रुपये दिए।", "Ramesh Kumar"),
                         ("फातिमा ने ढाई सौ रुपये जमा किए।", "Fatima"),
                         ("ಸೆಲ್ವಿ 32 ರೂಪಾಯಿ ಕೊಟ್ಟಳು", "Selvi")):
        client.put("/api/settings", json={"confirm_money": "always"})
        say(client, OWNER, phrase)
        preview = last_out(client, OWNER)
        check(f"native payment readback for {name}", name in preview["text"] and "jama" in preview["text"]
              and any(b[0].startswith("ok:") for b in preview["buttons"]), preview)
    for phrase in ("मेरा कितना बाकी है?", "ನನ್ನ ಬಾಕಿ ಎಷ್ಟು?"):
        say(client, RAMESH, phrase)
        check("native question reaches own balance", "250" in last_out(client, RAMESH)["text"])
    with patch.object(bolo.agent.planner, "plan", return_value=([{"tool": "add_credit", "args": {"name": "Selvi"}}], "fixture")):
        say(client, OWNER, "Selvi udhaar")
    incomplete = last_out(client, OWNER)
    check("missing amount offers edit", "₹?" in incomplete["text"] and
          any(b[0].startswith("fix:") for b in incomplete["buttons"]))
    for invalid in ("ok", "num:abc", "pick:1:900:2"):
        say(client, OWNER, button=invalid)
    for payload in ({"phone": {}}, {"phone": OWNER, "button": []}, {"phone": OWNER, "text": {}}, {"phone": "?"}):
        check("malformed simulator input is rejected", client.post("/api/simulate", json=payload).status_code == 400)
    with patch.object(bolo.agent.planner.llm, "json_call", return_value=({"actions": [{"tool":"add_credit","args":[]}]}, "fixture")):
        say(client, OWNER, "aaj ka hisaab")
        check("malformed model plan falls back to rules", "Aaj ka hisaab" in last_out(client, OWNER)["text"])
    client.put("/api/settings", json={"fanout_approval": "1"})
    say(client, OWNER, "delivery team se pucho kaun aa raha hai")
    check("fanout threshold uses resolved recipient count", "2 people" in
          client.get("/api/approvals").json()[0]["summary"])

# 12. onboarding from scratch: reset, first owner message configures the bot as a school
with TestClient(bolo.app) as client:
    rows_before = bolo.db.q("SELECT * FROM ledger ORDER BY id")
    archive = client.post("/api/reset").json()["archive"]
    check("reset archives every original row", bolo.db.q(f"SELECT * FROM {archive}_ledger ORDER BY id") == rows_before
          and not bolo.db.q("SELECT id FROM ledger"))
    client.put("/api/settings", json={"voice_replies": "0"})
    say(client, "919812345678", "Namaste, we run Sunrise Public School in Jayanagar, classes 1 to 7")
    prof = client.get("/api/profile").json()
    check("onboarded as school", prof["type"] == "school" and prof["onboarded"], prof)
    check("roles renamed (Parent)", prof["roles"]["customer"] == "Parent")
    check("attendance pack on", "attendance" in prof["features"])

print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
