# Demo stories (speak these into the mic)

These are role-play scripts, not canned answers: the bot isn't hard-coded to these lines. Change the names, items or amounts and it still works, because every reply is planned live from what was said and from the shop's own data.

Setup: **business side** (`http://localhost:8002`, log in as the shop, tick *fresh book* once before the demo) on the laptop screen; **customer side** (`http://localhost:8001`) on a second window or a phone. Pick the wireless mic in ⋮ → Microphone on each side. Every story below was run end to end through the live agent on 19 Nov 2026 (hosted planner; voice notes go through Sarvam + Groq speech first, typically 6–12 s per reply).

Each story is: **the jugaad today → what Bolo does → why it matters**.

---

## Story 1: "Two Rameshes" (the owner, by voice)
**Today:** the owner scribbles "Ramesh 450" in a notebook. There are two Rameshes. A month later nobody knows whose it was.

| Who | Says / taps | Bolo |
|---|---|---|
| Owner (business side, mic) | 🎙️ "Ramesh chaar sau pachaas ka saman liya, Shanivar dega" | Transcript appears under the voice note; "Which Ramesh?" with *Ramesh (milk-wala)* / *Ramesh Kumar* / *New* |
| Owner | taps **Ramesh (milk-wala)** | Card: "Ramesh +₹450 (chaar sau pachaas), due Sat" with ✅ Sahi / ✏️ Badlo |
| Owner | taps **✅ Sahi** | "Likh liya ✅ baaki ₹450" + a voice reply. The Khata gets a hash-chained entry with the original audio |

**Why it matters:** money is never written on a guess. The amount is read back in words, so "450" and "45" can't be confused.

## Story 2: "Order by voice" (the customer)
**Today:** the customer sends a voice note at rush hour; the owner hears it late or not at all.

| Who | Says / taps | Bolo |
|---|---|---|
| Lakshmi (customer side, mic) | 🎙️ "Bhaiya do packet atta aur ek Fortune oil bhej do" | "🛒 Aapka order samjha: 2 × Aashirvaad Atta ₹570, 1 × Fortune Oil ₹165, Total ₹735", then ✅ Order confirm / ✏️ Badlo / 💬 Kuch aur |
| Lakshmi | taps **✅ Order confirm** | "Order #N confirm, 30 min mein ready" |
| Owner (business side) | sees the ticket appear live; taps **📒 Udhaar mein likho** | Lakshmi gets "₹735 aapke khaate mein, baaki ₹…" |
| Owner | taps **📦 Packed** | Lakshmi gets "Aapka order ready hai!" |

**Why it matters:** the voice note became a priced, confirmed order and a khata entry. Nobody typed.

## Story 3: "It was 350, not 450" (the dispute)
**Today:** "maine 350 ka liya tha" vs "nahi, 450". Shouting, lost customer.

| Who | Says / taps | Bolo |
|---|---|---|
| Ramesh (customer side) | "kitna baaki hai" | Balance with entries + Pay now |
| Ramesh | 🎙️ "Galat hai, 350 tha" | Customer: "noted, shop will check". Owner: *Keep ₹450 / Change to ₹350* with the original recording |
| Owner | taps **Change** | A reversal row + new ₹350 row. The old entry stays visible: tamper-evident history |

**Why it matters:** the customer can question a charge, the owner has the final say, and both see the same record.

## Story 4: "I already paid on GPay"
| Who | Says / taps | Bolo |
|---|---|---|
| Lakshmi | 🎙️ "Maine do sau rupay GPay kar diye" | "Noted ₹200, shop will confirm" |
| Owner | gets "Lakshmi says she paid ₹200. Received?" → **✅ Mila** | Payment recorded; balance drops; Lakshmi is told |

## Story 5: "Who's coming Saturday?" (the team, instead of a WhatsApp group)
| Who | Says | Bolo |
|---|---|---|
| Owner | 🎙️ "Saturday 5 baje stock count, delivery team se pucho kaun aa raha hai" | Asks Ravi and Imran **privately**, each with Yes / No buttons, in their own language; live tally to the owner; nudges whoever is silent |

**Why it matters:** in a WhatsApp group, the question gets buried under forwards and nobody answers. Here every person gets a direct question and the owner gets a tally.

## Story 6 (closing line): the Khata Passport
Open the dashboard → Khata: every entry has its voice note, who agreed, and an intact hash chain. *"Lakshmi has repaid on time for months. Today that lives in a notebook no bank can see. With Bolo it's a record she can carry."*

## Story 7: "Tomato is 40 today, tell everyone" (the owner teaches the bot)
**Today:** the owner changes prices on a chalkboard; customers find out at the counter, or the owner types the same message 30 times.

| Who | Says | Bolo |
|---|---|---|
| Owner (business side, mic) | 🎙️ "Tomato ka rate ab 40 ho gaya, sabko bata do" | "✅ Price list update: Tomato ₹40/kg (pehle ₹30) · 5 customers ko bata diya" |
| Every customer | (no action) | "📢 Lakshmi Stores: price update · Tomato ₹40/kg", **each in their own language** |
| Any customer later | "tomato aaj kitne ka hai?" | "Tomato aaj ₹40 per kg hai": answered from the owner's list, not invented |
| Owner | 🎙️ "Yaad rakh: kal Sunday dukaan 2 baje band rahegi" | "📌 Yaad rakh liya": saved as shop knowledge |

**Why it matters:** the bot has **no data of its own**. Prices, timings and delivery rules come only from what the business tells it (by voice or in the dashboard), and every answer is grounded in that.

## Story 8: the customer who doesn't speak the shop's language
**Today:** a new tenant from another state messages in English or Tamil; the Kannada-speaking owner can't reply, so the sale is lost.

| Who | Says | Bolo |
|---|---|---|
| Priya (customer side, types or speaks English) | "Hi, how much is the Fortune oil today? Do you deliver?" | "Fortune Sunflower Oil 1 L is Rs 165. Yes, free delivery above Rs 300." |
| Priya | "Is the shop open tomorrow afternoon?" | "No, the shop closes at 2 pm tomorrow." (from Story 7's fact) |
| Priya | "Please send 1 Fortune oil and 2 Parle-G" | Priced order card with Confirm / Change / Other |
| Owner | sees Priya's order ticket in **Kannada** | Both sides speak their own language; amounts can't change in translation (number guard) |

## Why voice, not text (where voice notes are the only realistic input)
- **Hands are busy:** the kirana owner is weighing, packing or billing at rush hour; the delivery boy is on a scooter; the teacher is in class. Holding the mic button is faster than typing.
- **Literacy and script:** many owners and customers speak fluently but don't type comfortably in Kannada or Hindi script. Romanised typing is slow and ambiguous.
- **Mixed language:** "chaar sau pachaas", "dhai sau", "Shanivar dega": real speech mixes languages and number words that keyboards and forms don't handle.
- **It's already the habit:** customers already send voice notes to the shop. Bolo doesn't ask anyone to change; it makes the note count.
- Same engine, other voice-first jobs (profiles already built): a teacher sends a voice note "Ravi, Meena absent today" and attendance is marked, parents are told in their language; a clinic receptionist dictates appointment changes; a contractor records who came to the site.

---

## WhatsApp groups: what is and isn't possible
We checked what the real WhatsApp Business Platform allows, so the demo doesn't promise something WhatsApp can't do:
- A WhatsApp Business Platform (Cloud API) number **cannot be added to an ordinary WhatsApp group** like a personal contact, and it cannot read group chats it isn't part of.
- Meta has started offering a **Groups API** for the Cloud API: the *business* creates the group and people join through an invite link. It has eligibility rules and size limits, so it suits small teams, not big community groups.
- Business-initiated messages outside the 24-hour customer-service window need pre-approved **templates**. Free-form replies are only allowed within 24 hours of the person's last message.

**So Bolo's design:** private 1:1 chats with every customer and team member (always allowed), and *group-style* tasks (polls, announcements, "who's coming?") fanned out privately with a shared tally. If a business gets Groups API access, the same agent can sit in a business-created group and reply only when someone sends a voice note or mentions it. In the simulator, Story 5 shows the fan-out version.

## Limits we hit today (paperwork, not code)
- Twilio trial number: inbound works; replies are blocked (21654 "ContentSid Required", 12300), and trials can't create templates.
- Meta WhatsApp test number: the new account needed a one-hour cooldown to create a business portfolio.
- Free-tier AI quotas: occasional 429s. The planner falls back Gemini → Sarvam → Groq → offline rules, and speech can run on a local GPU (faster-whisper).
