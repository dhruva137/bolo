"""Contacts, roles and name resolution across scripts.

"Ramesh", "ರಮೇಶ್", "रमेश", "Rameshanna", "Ramesh bhaiya" and a nickname like "milk-wala Ramesh"
should all find the same person, and two real Rameshes must trigger a question, not a guess.
"""
import json
import re
import unicodedata

from rapidfuzz import fuzz

import db

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate as _xlit
except Exception:  # library is optional
    sanscript = None

HONORIFICS = r"\b(bhaiya|bhai|anna|akka|ji|sir|madam|aunty|uncle|saar|avare|garu|amma|appa|didi|bhabhi)\b"
SUFFIXES = ("anna", "akka", "bhai", "ji", "avaru", "garu")


def romanize(text: str) -> str:
    t = text or ""
    if sanscript:
        if re.search(r"[ऀ-ॿ]", t):
            t = _xlit(t, sanscript.DEVANAGARI, sanscript.ITRANS)
        elif re.search(r"[ಀ-೿]", t):
            t = _xlit(t, sanscript.KANNADA, sanscript.ITRANS)
        elif re.search(r"[஀-௿]", t):
            t = _xlit(t, sanscript.TAMIL, sanscript.ITRANS)
        elif re.search(r"[ఀ-౿]", t):
            t = _xlit(t, sanscript.TELUGU, sanscript.ITRANS)
    # ITRANS can keep diacritics for short Kannada vowels. Keep the vowel
    # when folding it to Latin so spoken names stay close to catalog spellings.
    t = unicodedata.normalize("NFKD", t).lower().replace("ph", "f")
    t = re.sub(HONORIFICS, " ", t)
    t = re.sub(r"[^a-z ]", "", t)
    t = t.replace("aa", "a").replace("ee", "i").replace("oo", "u")
    words = []
    for w in t.split():
        for s in SUFFIXES:  # "rameshanna" -> "ramesh"
            if w.endswith(s) and len(w) > len(s) + 2:
                w = w[: -len(s)]
                break
        words.append(w.rstrip("a") if len(w) > 3 else w)  # "ramesha" -> "ramesh"
    return " ".join(words).strip()


def all_contacts(role: str | None = None) -> list[dict]:
    rows = db.q("SELECT * FROM contacts" + (" WHERE role=?" if role else "") + " ORDER BY name", (role,) if role else ())
    for r in rows:
        r["aliases"] = json.loads(r["aliases"] or "[]")
    return rows


def get(cid: int) -> dict | None:
    r = db.q1("SELECT * FROM contacts WHERE id=?", (cid,))
    if r:
        r["aliases"] = json.loads(r["aliases"] or "[]")
    return r


def by_phone(phone: str) -> dict | None:
    r = db.q1("SELECT id FROM contacts WHERE phone=?", (normalize_phone(phone),))
    return get(r["id"]) if r else None


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def upsert(name: str, phone: str = "", role: str = "customer", lang: str = "hi-IN", aliases=None,
           credit_limit: float = 0, opted_in: int = 0, note: str = "", cid: int | None = None) -> dict:
    phone = normalize_phone(phone) or None
    aliases_json = json.dumps(aliases or [], ensure_ascii=False)
    if cid:
        db.run("UPDATE contacts SET name=?, phone=?, role=?, lang=?, aliases=?, credit_limit=?, opted_in=?, note=?"
               " WHERE id=?", (name, phone, role, lang, aliases_json, credit_limit, opted_in, note, cid))
        return get(cid)
    existing = by_phone(phone) if phone else None
    if existing:
        return existing
    new_id = db.run("INSERT INTO contacts(name, phone, role, lang, aliases, credit_limit, opted_in, note, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (name, phone, role, lang, aliases_json, credit_limit, opted_in, note, db.now()))
    return get(new_id)


def add_alias(cid: int, alias: str) -> None:
    c = get(cid)
    if c and alias and alias.lower() not in [a.lower() for a in c["aliases"]] and alias.lower() != c["name"].lower():
        db.run("UPDATE contacts SET aliases=? WHERE id=?", (json.dumps(c["aliases"] + [alias], ensure_ascii=False), cid))


def find(name_said: str, role: str | None = None, limit: int = 3) -> list[dict]:
    """Return candidates [{contact, score}] best first. Score 0..100."""
    said = romanize(name_said)
    if not said:
        return []
    out = []
    exact = []
    for c in all_contacts(role):
        names = [c["name"], *c["aliases"]]
        forms = [romanize(n) for n in names]
        if " " in said and said in forms:
            exact.append({"contact": c, "score": 100.0})
        best = max(max(fuzz.WRatio(said, form), fuzz.token_set_ratio(said, form)) for form in forms)
        out.append({"contact": c, "score": round(best, 1)})
    # A complete full name outranks a matching first name. A first name alone
    # still goes through normal ambiguity checks when two customers share it.
    if exact:
        return exact[:limit]
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def resolve(name_said: str, role: str | None = "customer") -> dict:
    """{'status': 'ok'|'ambiguous'|'new', 'contact': ..., 'candidates': [...]}"""
    cands = find(name_said, role)
    if not cands or cands[0]["score"] < 70:
        return {"status": "new", "contact": None, "candidates": cands}
    top = cands[0]
    close = [c for c in cands[1:] if c["score"] >= 70 and top["score"] - c["score"] < 8]
    if close:
        return {"status": "ambiguous", "contact": None, "candidates": [top, *close]}
    return {"status": "ok", "contact": top["contact"], "candidates": cands}


def label(c: dict) -> str:
    """Short, distinguishing label for buttons (≤ 20 chars)."""
    hint = c.get("note") or (c["aliases"][0] if c.get("aliases") else "") or (c.get("phone") or "")[-4:]
    return f"{c['name']} ({hint})"[:20] if hint else c["name"][:20]


def owner() -> dict | None:
    r = db.q1("SELECT id FROM contacts WHERE role='owner' LIMIT 1")
    return get(r["id"]) if r else None
