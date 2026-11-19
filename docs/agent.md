# The Bolo agent

Bolo is not a transcription bot. It is an agent that **listens, cleans, understands, double-checks, acts, and follows up**: it runs the shop's credit and orders the way a sharp munshi (bookkeeper) would.

## Who talks to it
- **Primary: the shopkeeper.** They send Bolo voice notes all day, the way they would talk to a munshi: "Ramesh ne 450 ka saman liya, Shanivar dega" ("Ramesh took ₹450 of goods, will pay Saturday"); "Lakshmi ne 200 diye" ("Lakshmi paid 200"); "sugar khatam ho raha hai, 10 kilo mangao" ("sugar is running out, order 10 kg"); "aaj kitna baaki hai?" ("how much is owed today?"). This is the notebook jugaad, and the shopkeeper is an opted-in business user, so there's no consent problem.
- **Secondary: customers who opt in.** A customer who messages the shop's Bolo number (or scans the counter QR) can send voice orders, ask "kitna baaki?", and confirm credit by voice. Customers who never opt in get nothing from Bolo; the shopkeeper still has their ledger.

## Pipeline
```
voice note ─► 1 CLEAN ─► 2 HEAR (dual) ─► 3 NORMALIZE ─► 4 UNDERSTAND (agent + tools) ─► 5 VERIFY (risk-tiered) ─► 6 ACT ─► 7 FOLLOW UP
```

### 1. Clean (noise reduction, on CPU, < 1 s)
Shops are loud: traffic, pressure cookers, TVs, other customers.
- Default: an ffmpeg chain with a high-pass to cut fan and traffic rumble, a low-pass, an FFT denoise, and loudness normalization, resampled to 16 kHz mono.
- Upgrade: DeepFilterNet (neural speech enhancement, CPU).
- We keep the original audio as evidence and transcribe the cleaned audio.

### 2. Hear twice (dual-engine speech-to-text)
- **Engine A: Sarvam Saaras v4** (`codemix` mode, auto language ID), with **`keyterms` = this shop's customer names and top products**, so recognition is grounded in the shop's world.
- **Engine B: an independent engine** (Groq Whisper large-v3-turbo or Gemini audio).
- **Cross-check:** names and numbers are compared across the two transcripts. If they agree, confidence goes up. If they disagree, Bolo asks.

### 3. Normalize (deterministic, not AI)
- **Spoken numbers in Indian languages:**
  - Hindi: dedh sau 150, dhai sau 250, saade teen sau 350, sawa, paune
  - Kannada: nooru 100, ondu-vare 1.5
  - Tamil / Telugu equivalents
  - "450 rupees" said half in English, half in Hindi
- **Confusable-number guard:** pairs that speech engines mix up get flagged:
  - pachaas 50 / pachattar 75
  - saath 60 / sattar 70
  - chaalis 40 / chauvalis 44
  - Kannada aivattu 50 / eppattu 70
- **Dates:** "Shanivar", "next week", "month end", "Ugadi ke baad" all become a real due date.
- **Names:** transliterated across scripts, then fuzzy-matched to the customer book (Ramesh / ರಮೇಶ್ / रमेश).

### 4. Understand (an agent with tools, not a single prompt)
The LLM (Gemini Flash with function calling; Groq-hosted open model as fallback) chooses tools:
| Tool | What it does |
|---|---|
| `find_customer(name_said)` | fuzzy + phonetic match; returns candidates with scores |
| `add_credit(customer, amount, items?, due?)` | pending until verified |
| `record_payment(customer, amount, mode)` | cash / UPI; "claimed" until the shopkeeper confirms |
| `create_order(customer, items[])` | items matched to the catalog |
| `get_balance(customer?)` | one customer or everyone |
| `set_reminder(customer, when)` | schedules a reminder |
| `restock(item, qty)` | draft purchase order to the distributor |
| `read_document(media_id)` | invoice/bill photo → fields (Sarvam Vision) |
| `ask_user(question, options)` | clarification as voice + buttons |
One voice note can trigger several tools: "Ramesh ne 450 liya, Lakshmi ne 200 diye, aur sugar mangao" becomes three actions, each verified.

### 5. Verify (double verification when it matters)
Every action gets a **risk score**. Low-risk actions commit silently; high-risk ones are read back.
| Trigger | What Bolo does |
|---|---|
| amount ≥ ₹500 (configurable) or the number is in a confusable pair | read back the amount **as a numeral and in words** in the user's language: "₹450, chaar sau pachaas. Sahi?" |
| the two STT engines disagree on a name or number | "Did you say 50 or 75?" with buttons [₹50] [₹75] |
| two Rameshes, or a new name | "Kaunsa Ramesh? [Ramesh (milk-wala)] [Ramesh Kumar] [New customer]" |
| low recognition confidence / heavy noise | "Ek baar phir boliye?" ("say it once more?"), with the transcript shown |
| payment the customer claims | stays *claimed* until the shopkeeper taps ✅ |
| credit for an opted-in customer | the customer gets "₹450 udhaar likha gaya. Sahi hai?" and their "haan" or ✅ is stored with the entry (two-sided consent) |
Confirmations are always **voice + text + buttons**. Research on low-literacy users shows speech alone isn't reliable for critical entries, so a tap fallback is always there.

### 6. Act
- An **append-only, hash-chained ledger**. Each entry stores the original audio's fingerprint, the transcript, who confirmed it, and how.
- Order tickets and pick-lists go to the console. Restock items become a draft purchase order (PDF) for the distributor.
- An undo window: "galat tha, hatao" ("that was wrong, remove it") reverses the last entry within 10 minutes. The reversal is itself recorded.

### 7. Follow up (this is what makes it a process redesign, not a transcriber)
- **Before the due date:** a polite reminder in the customer's language (opted-in customers via a utility template; others get a ready-to-forward voice note the shopkeeper sends from their own phone).
- **Feature-phone customers:** an optional voice-call reminder via a voice-agent platform (Bolna) as a roadmap item.
- **9 pm daily summary** to the shopkeeper by voice: "Aaj ₹3,200 udhaar diya, ₹1,800 wapas aaya. 3 log 30 din se zyada." ("Today ₹3,200 given on credit, ₹1,800 came back. 3 people are over 30 days.")
- **Risk flags:** customers whose balance keeps growing, frequent late payers, credit limits per customer ("Ramesh ka limit 2,000 cross ho gaya", "Ramesh is over his ₹2,000 limit").
- **Statement PDF** on request, in the customer's language.

## The hard parts, and how Bolo answers each
| Hard part | Answer |
|---|---|
| Ambiguous or misheard names | keyterms in STT + transliteration + fuzzy/phonetic match + disambiguation buttons + nicknames ("milk-wala Ramesh") |
| Wrong amounts (pachaas vs pachattar) | dual-engine cross-check + confusable-pair guard + read-back as numeral **and** words + buttons |
| Noise | ffmpeg/DeepFilterNet cleanup + a "say again" path; evaluated on recordings with real shop noise |
| Customer consent | the shopkeeper is the primary user; customers are messaged only after they message first or opt in at the counter; reminders use approved utility templates |
| WhatsApp API constraints | official Cloud API; replies within the 24-hour service window; templates for reminders; test number limited to 5 verified recipients for the demo |
| Trust in the record | append-only, hash-chained, audio-backed ledger; `/ledger/verify` integrity check; dispute playback |

## How we measure it
A recorded test set (several languages, real shop noise, confusable amounts on purpose) scored on **action accuracy**: right customer, right amount, right type. We compare single-engine STT, dual-engine STT, and dual-engine + verification. Results go in [`../eval/`](../eval/).
