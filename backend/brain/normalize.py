"""Deterministic normalization of spoken Indian numbers, dates and fractions.

Speech engines are weak at numbers (see indic-punct, arXiv 2203.16825), so we never let the
LLM be the only judge of an amount. This module:
  * converts number words (Hindi, Kannada, Tamil, Telugu, English; Latin or native script) to digits
  * understands Indian fractions: dedh 1.5, dhai 2.5, saade N = N+0.5, sawa N = N+0.25, paune N = N-0.25
  * flags amounts that speech engines commonly confuse (50/75, 60/70, 40/44, ...)
  * turns "Shanivar", "kal", "next week", "month end" into a date
"""
import datetime as dt
import math
import re

ONES = {
    # Hindi / Hinglish
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "chah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "baarah": 12, "terah": 13,
    "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17, "atharah": 18, "unnis": 19, "bees": 20, "pachchis": 25,
    "pachees": 25, "tees": 30, "chalis": 40, "chaalis": 40, "chawalis": 44, "chauvalis": 44, "pachas": 50,
    "pachaas": 50, "saath": 60, "sattar": 70, "pachattar": 75, "pachhattar": 75, "assi": 80, "nabbe": 90, "nabbey": 90,
    # Kannada
    "ondu": 1, "eradu": 2, "mooru": 3, "naalku": 4, "nalku": 4, "aidu": 5, "aaru": 6, "elu": 7, "entu": 8, "ombattu": 9,
    "hattu": 10, "ippattu": 20, "muvattu": 30, "nalavattu": 40, "aivattu": 50, "aravattu": 60, "eppattu": 70,
    "embattu": 80, "tombattu": 90,
    # Tamil / Telugu (common)
    "onnu": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5, "pathu": 10, "aimbadhu": 50, "okati": 1, "padi": 10,
    "yabhai": 50, "vanda": 100,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "seventyfive": 75,
    "eighty": 80, "ninety": 90,
}
MULT = {"sau": 100, "nooru": 100, "noor": 100, "hundred": 100, "nuru": 100, "nooraru": 100,
        "hazaar": 1000, "hazar": 1000, "saavira": 1000, "savira": 1000, "thousand": 1000, "aayiram": 1000,
        "lakh": 100000, "laakh": 100000}
FRACTIONS = {"dedh": 1.5, "dhai": 2.5, "adhai": 2.5, "aadha": 0.5, "adha": 0.5, "ardha": 0.5, "ondu-vare": 1.5,
             "onduvare": 1.5, "half": 0.5}
MODIFIERS = {"saade": 0.5, "sade": 0.5, "sawa": 0.25, "sava": 0.25, "paune": -0.25, "pone": -0.25}

# Native-script words that map to the romanized forms above (most frequent ones).
NATIVE = {
    "सौ": "sau", "हज़ार": "hazaar", "हजार": "hazaar", "डेढ़": "dedh", "ढाई": "dhai", "साढ़े": "saade", "सवा": "sawa",
    "पौने": "paune", "पचास": "pachaas", "पचहत्तर": "pachattar", "साठ": "saath", "सत्तर": "sattar", "चालीस": "chaalis",
    "एक": "ek", "दो": "do", "तीन": "teen", "चार": "chaar", "पांच": "paanch", "पाँच": "paanch", "दस": "das", "बीस": "bees",
    "ನೂರು": "nooru", "ಸಾವಿರ": "saavira", "ಒಂದು": "ondu", "ಎರಡು": "eradu", "ಮೂರು": "mooru", "ನಾಲ್ಕು": "naalku",
    "ಐದು": "aidu", "ಹತ್ತು": "hattu", "ಐವತ್ತು": "aivattu", "ಎಪ್ಪತ್ತು": "eppattu", "ಅರ್ಧ": "ardha",
}

# Pairs speech engines mix up; an amount containing either side is read back with buttons.
CONFUSABLE = [(50, 75), (60, 70), (40, 44), (13, 30), (14, 40), (15, 50), (16, 60), (17, 70), (18, 80), (19, 90)]

WEEKDAYS = {
    "monday": 0, "somvar": 0, "somavara": 0, "tuesday": 1, "mangalvar": 1, "mangalavara": 1,
    "wednesday": 2, "budhvar": 2, "budhavara": 2, "thursday": 3, "guruvar": 3, "guruvara": 3,
    "friday": 4, "shukravar": 4, "shukravara": 4, "saturday": 5, "shanivar": 5, "shanivara": 5,
    "sunday": 6, "ravivar": 6, "itvaar": 6, "ravivara": 6,
    "सोमवार": 0, "मंगलवार": 1, "बुधवार": 2, "गुरुवार": 3, "शुक्रवार": 4, "शनिवार": 5, "रविवार": 6,
    "ಸೋಮವಾರ": 0, "ಮಂಗಳವಾರ": 1, "ಬುಧವಾರ": 2, "ಗುರುವಾರ": 3, "ಶುಕ್ರವಾರ": 4, "ಶನಿವಾರ": 5, "ಭಾನುವಾರ": 6,
}


def _tokens(text: str) -> list[str]:
    t = text
    for k, v in NATIVE.items():
        t = t.replace(k, f" {v} ")
    t = re.sub(r"(\d),(\d)", r"\1\2", t)  # 1,200 -> 1200
    t = re.sub(r"₹\s*", " ", t)
    return re.findall(r"[a-zA-Z\-]+|\d+(?:\.\d+)?|[^\sa-zA-Z\d]+", t.lower())


def words_to_numbers(text: str) -> tuple[str, list[float]]:
    """Return (text with number phrases replaced by digits, list of numbers found in order)."""
    toks = _tokens(text)
    out, nums = [], []
    i = 0
    while i < len(toks):
        j, total, cur, mod = i, 0.0, 0.0, 0.0
        while j < len(toks):
            w = toks[j]
            if w in MODIFIERS:
                mod += MODIFIERS[w]  # saade teen sau = (3 + 0.5) * 100
            elif w in FRACTIONS:
                cur += FRACTIONS[w]  # dedh sau = 1.5 * 100
            elif re.fullmatch(r"\d+(?:\.\d+)?", w):
                cur += float(w)
            elif w in ONES:
                cur += ONES[w]
            elif w in MULT and (cur or mod):
                total += ((cur or 1) + mod) * MULT[w]  # chaar sau pachaas = 4*100+50; sawa sau = 1.25*100
                cur, mod = 0.0, 0.0
            elif w in MULT and not total:
                total += MULT[w]  # "sau rupaye" = 100
            else:
                break
            j += 1
        value = round(total + cur + (mod if cur else 0), 2)
        if j > i and value and math.isfinite(value):
            nums.append(value)
            out.append(str(int(value)) if value == int(value) else str(value))
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out), nums


def confusable(amount: float) -> bool:
    a = int(amount)
    parts = {a % 100, (a // 100) % 100, a}
    return any(x in parts or y in parts for x, y in CONFUSABLE)


def in_words_hi(amount: float) -> str:
    """Short Hindi read-back of an amount, e.g. 450 -> 'chaar sau pachaas'."""
    rev = {v: k for k, v in ONES.items() if k in (
        "ek", "do", "teen", "chaar", "paanch", "chhe", "saat", "aath", "nau", "das", "gyarah", "barah", "terah", "chaudah",
        "pandrah", "solah", "satrah", "atharah", "unnis", "bees", "pachchis", "tees", "chaalis", "chauvalis", "pachaas",
        "saath", "sattar", "pachattar", "assi", "nabbe")}
    a = int(round(amount))
    parts = []
    if a >= 1000:
        parts.append(f"{rev.get(a // 1000, a // 1000)} hazaar")
        a %= 1000
    if a >= 100:
        parts.append(f"{rev.get(a // 100, a // 100)} sau")
        a %= 100
    if a:
        parts.append(str(rev.get(a, a)))
    return " ".join(parts) or "zero"


def parse_date(text: str, today: dt.date | None = None) -> str:
    """Best-effort due date (ISO) from a phrase; '' if none."""
    today = today or dt.date.today()
    t = text.lower()
    for w, wd in WEEKDAYS.items():
        if w in t:
            delta = (wd - today.weekday()) % 7 or 7
            return (today + dt.timedelta(days=delta)).isoformat()
    if re.search(r"\b(kal|naale|tomorrow|repu)\b", t) or "कल" in t or "ನಾಳೆ" in t:
        return (today + dt.timedelta(days=1)).isoformat()
    if re.search(r"\b(parso|naadidu)\b", t):
        return (today + dt.timedelta(days=2)).isoformat()
    if re.search(r"next week|agle hafte|mundina vara", t):
        return (today + dt.timedelta(days=7)).isoformat()
    if re.search(r"month end|mahine ke end|tingala koneg|end of month", t):
        nxt = (today.replace(day=28) + dt.timedelta(days=4))
        return (nxt - dt.timedelta(days=nxt.day)).isoformat()
    m = re.search(r"\b(\d{1,2})\s*(tarikh|tareekh|taarikh|date)\b", t)
    if m:
        d = int(m.group(1))
        try:
            cand = today.replace(day=d)
            if cand < today:
                cand = (today.replace(day=28) + dt.timedelta(days=4)).replace(day=d)
            return cand.isoformat()
        except ValueError:
            return ""
    return ""


def numbers_disagree(a: str, b: str) -> list[tuple[float, float]]:
    """Compare numbers heard by two engines; return mismatched pairs (in order)."""
    _, na = words_to_numbers(a or "")
    _, nb = words_to_numbers(b or "")
    if not na or not nb:
        return []
    return [(x, y) for x, y in zip(na, nb) if abs(x - y) > 0.01]
