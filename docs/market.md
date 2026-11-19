# Market and go-to-market

Assumptions are marked (est.) and will be replaced with pilot data.

## Positioning
**"Your shop keeps talking on WhatsApp. Bolo keeps the books."**
For kirana owners who take orders and give udhaar over WhatsApp voice notes, Bolo turns every voice note — in any language — into an order ticket and a provable credit entry, and talks back to the customer in their language. Unlike Khatabook/OkCredit (type-it-yourself ledgers) or ordering apps (customers must change behaviour), **nobody changes behaviour: they keep talking.**

## Who (beachhead)
- **Primary:** Bengaluru kiranas with 30–150 regular credit customers and a WhatsApp ordering habit (residential pockets: Jayanagar, Koramangala, HSR, Whitefield, Malleshwaram). Multilingual customers (Kannada, Hindi, Tamil, Telugu, English) = our edge.
- **Secondary users (viral side):** their customers — they receive voice receipts and reminders.
- Later skins on the same engine: domestic-worker wages, water tankers, clinics, society maintenance.

## Pain → value (put numbers from our micro-survey here)
| Pain | Value |
|---|---|
| Missed/wrong orders at rush hour | Auto pick-list; every note becomes a ticket |
| Udhaar disputes and forgotten dues | Audio-backed tamper-evident ledger; automatic voice reminders |
| Owner can't listen to 40 notes | Read-back confirms with the customer, not the owner |
| Notebook lost = money lost | Ledger lives in the cloud, exportable |
Impact we will measure in pilots: share of previously written-off udhaar recovered, and minutes per day saved on listening to voice notes.

## Distribution (cheap, India-native)
1. **FMCG distributor salesmen** visit 30–60 kiranas a day — partner with a distributor; Bolo onboarding in 2 minutes during their visit (scan QR, send one voice note). Distributor gets anonymised demand signals (with consent).
2. **Customer-side virality:** every voice receipt ends with "Bolo se bheja gaya" → customers ask other shops for it.
3. **WhatsApp-native onboarding:** shop forwards one voice note to the Bolo number → instantly sees it as a ticket. Aha in < 60 s.
4. **Local shopkeeper associations / trader WhatsApp groups**, kirana wholesale markets (KR Market, Chickpet).
5. **Content:** 15-second reels in Kannada/Hindi: "Udhaar ka jhagda khatam."
6. **Pilot loop:** 10 shops near one campus/apartment cluster → case study with real numbers → next 100.

## Business model
- **Freemium:** free up to 100 voice notes/month.
- **Bolo Pro ₹149/month (est.):** unlimited notes, voice reminders, statements, export, multiple staff.
- **Recovery fee (optional):** small % of udhaar recovered via reminders/UPI links.
- **Later:** credit data (with explicit consent) → working-capital loans for shops via NBFC partners; distributor reorder intelligence.
- Unit cost check: STT ~₹30/hour of audio (Sarvam list price) → a 15 s note ≈ ₹0.13; 1,000 notes/month ≈ ₹125 STT + LLM/TTS (est.) → Pro must be priced/limited to stay margin-positive.

## Competition
| Player | What they do | Why we win |
|---|---|---|
| Khatabook / OkCredit / Vyapar | Digital khata, owner types | Zero typing; customer participates; voice proof |
| JioMart / quick commerce | Customer switches to app | Customer keeps WhatsApp habit |
| WhatsApp Business catalog | Text/catalog orders | Doesn't parse voice or keep ledger |
| Jugalbandi / Bhashini bots | Q&A voice bots | We create transactions in a system of record |
Moats: multilingual voice grounding on each shop's catalog/customers; audio-backed ledger history; distributor channel.

## Risks & answers
- *WhatsApp API costs/policy* → business-initiated messages cost per conversation; we reply within the 24h service window (customer-initiated) and use PWA share path as fallback.
- *Privacy* → audio stored per shop, encrypted at rest (roadmap), consent line in first reply, delete on request; no data sold without opt-in.
- *ASR errors* → confidence gate + read-back; never silently commits low-confidence money.
- *Shopkeeper adoption* → zero-learning: they forward one voice note.

## Metrics we'd track
Activation (first ticket in < 60 s), weekly active shops, notes/shop/day, % auto-committed, correction rate, udhaar recovered ₹, D30 retention.

## 30-second close
"Thirteen million kiranas run on voice notes and a notebook. We didn't ask them to change. We made their voice the system."

## Partners, not threats
| Player | Gap | How Bolo works with them |
|---|---|---|
| Khatabook, OkCredit | owner types every entry; customer never confirms | Bolo is their **voice front door**: entries export via API/CSV |
| Flipkart × Sarvam wholesale voice ordering | covers kirana → supplier only | low stock triggers a voice restock order **upstream** |
| Sarvam (Saaras STT, Bulbul TTS) | enterprise WhatsApp agents | Bolo's speech engine; we bring the small-merchant long tail |
| ONDC seller apps (e.g. Kiko Live) | catalog taps, no voice, no credit | voice-captured orders published into the network |
| SuperK, Apna Mart, KiranaPro | own apps, no credit | B2B channel: one deal reaches hundreds of stores |
| Meta Business AI | answers questions, keeps no records | Bolo is the record-keeping layer on the WhatsApp Cloud API |
| Interakt, Wati, Gupshup, AiSensy | generic, priced above kiranas, no ledger | messaging rails and marketplace distribution |
Storefront-app players (Dukaan, Bikayi) moved away from kiranas. That supports Bolo's choice to stay inside WhatsApp with no new app. Quick commerce offers no credit and no relationship, and udhaar is the kirana's edge. Bolo makes that edge digital.

## Unit economics and compliance
- WhatsApp has used per-message pricing since July 2025, and **messages from customers are free**. From October 2026 the first 1,000 service replies per number each month are free. Utility reminders cost about ₹0.12 each in India (vendor-quoted rate).
- Speech-to-text costs about ₹0.49 a minute (Sarvam list price), so a 15-second note is about ₹0.12. Text-to-speech is about ₹3 per 1,000 characters. **That comes to under ₹1 per order (est.).**
- Meta's January 2026 policy bans general-purpose AI chatbots on WhatsApp but allows bots tied to a specific business. Bolo is each shop's own ordering and khata assistant.
- Bolo uses the official Cloud API only. Customers start the conversation, which gives opt-in for service replies. Reminders use approved utility templates and require explicit opt-in.

## Beyond kiranas
Any small business that runs operations on voice notes: distributors, contractors, caterers, tuition centres, clinics (non-medical operations), housing societies. Each business brings its staff, partners, suppliers and customers onto Bolo, and every recipient is a potential next customer.

## Cost to serve (per busy business per month, est.)
| Item | ₹ |
|---|---|
| Speech-to-text (≈900 notes × 15 s at ₹0.49/min) | ~110 |
| Language model | ~20–50 |
| Voice replies (Bulbul v4-flash, ₹1 per 1,000 chars) | ~135 |
| WhatsApp utility messages | ~40 |
| Phone-call escalations (~20 min) | ~100 |
| Hosting | ~30 |
| **Total** | **~₹450–500** |

**Pricing (est.):** Free (50 notes, khata only) · Dukaan ₹299/month · Business ₹999/month (team roles, templates, smart polls, call escalation) · per-seat for distributors. Recovering a single ₹1,000 due in a month pays for the Business plan.
