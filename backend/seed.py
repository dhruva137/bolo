"""Demo seed: a believable Bengaluru kirana. Safe to run more than once."""
import db
from core import contacts as C
from core import ledger

PEOPLE = [
    # name, phone, role, lang, aliases, note, limit
    ("Manjunath", "919900000001", "owner", "kn-IN", ["Manju"], "owner", 0),
    ("Kiran", "919900000002", "staff", "kn-IN", [], "son", 0),
    ("Ravi", "919900000003", "delivery", "kn-IN", [], "delivery", 0),
    ("Imran", "919900000004", "delivery", "hi-IN", [], "delivery", 0),
    ("Suresh", "919900000005", "staff", "ta-IN", [], "helper", 0),
    ("Prakash", "919900000006", "partner", "kn-IN", [], "partner", 0),
    ("Sri Balaji Traders", "919900000007", "supplier", "kn-IN", ["Balaji"], "supplier", 0),
    ("Ramesh", "919900000011", "customer", "hi-IN", ["Rameshanna", "milk-wala"], "milk-wala", 2000),
    ("Ramesh Kumar", "919900000012", "customer", "kn-IN", [], "3rd cross", 2000),
    ("Lakshmi", "919900000013", "customer", "kn-IN", ["Lakshmi akka"], "", 3000),
    ("Fatima", "919900000014", "customer", "hi-IN", [], "", 1500),
    ("Selvi", "919900000015", "customer", "ta-IN", [], "", 1500),
]
PRODUCTS = [("Aashirvaad Atta 5kg", "atta, aata, hittu", "pack", 285), ("Fortune Sunflower Oil 1L", "fortune, tel, oil, enne", "pack", 165),
            ("Nandini Milk 500ml", "haalu, doodh, milk", "pack", 26), ("Sugar", "sakkare, cheeni", "kg", 46),
            ("Toor Dal", "togari bele, arhar dal", "kg", 160), ("Parle-G", "biscuit", "pack", 10),
            ("Rice Sona Masoori", "akki, chawal", "kg", 62), ("Tomato", "tamatar, tomato", "kg", 30),
            ("Onion", "eerulli, pyaaz", "kg", 40), ("Cement bag", "cement", "bag", 380)]


SCHOOL = [
    ("Mrs. Rao", "919900000101", "owner", "kn-IN", ["Principal"], "principal", 0),
    ("Anita", "919900000102", "staff", "kn-IN", ["Anita maam"], "Class 5 teacher", 0),
    ("Joseph", "919900000103", "staff", "en-IN", ["Joseph sir"], "Maths", 0),
    ("Raju", "919900000104", "delivery", "kn-IN", [], "van driver", 0),
    ("Riya (parent)", "919900000111", "customer", "hi-IN", ["Riya"], "Class 5", 0),
    ("Aarav (parent)", "919900000112", "customer", "kn-IN", ["Aarav"], "Class 5", 0),
    ("Meena (parent)", "919900000113", "customer", "ta-IN", ["Meena"], "Class 3", 0),
]


def run(kind: str = "kirana") -> dict:
    db.init()
    from features import knowledge, profiles
    knowledge.init()
    if kind == "school":
        profiles.apply("We run Sunrise Public School in Jayanagar, classes 1 to 7, about 300 students. Parents talk on WhatsApp.",
                       "Sunrise Public School", "school")
        for name, phone, role, lang, aliases, note, limit in SCHOOL:
            C.upsert(name, phone, role, lang, aliases, limit, 1, note)
        owner = C.by_phone("919900000101")
        db.set_setting("owner_phone", owner["phone"])
        knowledge.add_fact("Timings", "School timings 8:30 am to 3:00 pm, Monday to Saturday. Office open till 4 pm.", "customer")
        knowledge.add_fact("Fees", "Term fee Rs 14,500 for classes 1-5 and Rs 16,000 for 6-7. Due by the 10th of the first month.", "customer")
        if not db.q1("SELECT id FROM ledger LIMIT 1"):
            ledger.add(C.by_phone("919900000111")["id"], 4500, "credit", note="Term 2 fee balance", actor=owner["phone"])
        return {"ok": True, "kind": kind, "contacts": len(C.all_contacts()), "owner": owner["phone"]}
    profiles.apply("Lakshmi Stores is a kirana shop in Jayanagar. Customers order by WhatsApp voice notes and buy on credit (udhaar).",
                   "Lakshmi Stores", "kirana")
    knowledge.add_fact("Timings", "Open 7 am to 10 pm every day. Home delivery within 2 km, free above Rs 300.", "customer")
    for name, phone, role, lang, aliases, note, limit in PEOPLE:
        existing = C.by_phone(phone)
        c = C.upsert(name, phone, role, lang, aliases, limit, 1, note)
        # These two fictional delivery workers illustrate different reply preferences.
        if not existing and name in ("Ravi", "Imran"):
            mode = "voice" if name == "Ravi" else "text"
            db.run("UPDATE contacts SET reply_mode=? WHERE id=?", (mode, c["id"]))
    if not db.q1("SELECT id FROM catalog LIMIT 1"):
        for n, a, u, p in PRODUCTS:
            db.run("INSERT INTO catalog(name, aliases, unit, price) VALUES (?,?,?,?)",
                   (n, str([x.strip() for x in a.split(",")]).replace("'", '"'), u, p))
    owner = C.by_phone("919900000001")
    db.set_setting("owner_phone", owner["phone"])
    if not db.q1("SELECT id FROM ledger LIMIT 1"):
        old = db.now() - 35 * 86400
        for name, amt in (("Ramesh Kumar", 790), ("Lakshmi", 450), ("Fatima", 320)):
            c = C.by_phone({"Ramesh Kumar": "919900000012", "Lakshmi": "919900000013", "Fatima": "919900000014"}[name])
            ledger.add(c["id"], amt, "credit", note="opening balance", actor=owner["phone"],
                       created_at=old if name == "Ramesh Kumar" else None)
    return {"ok": True, "contacts": len(C.all_contacts()), "owner": owner["phone"]}


if __name__ == "__main__":
    print(run())
