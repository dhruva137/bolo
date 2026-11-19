# Pitch: Bolo (winning demo, angle, GTM, Q&A)

> One line: **India's shops keep talking on WhatsApp. Bolo turns every voice note into a record both sides agree on, and that record becomes credit history for people no bank can see.**

## 1. The break (30 s)
A kirana gives ₹2–5 lakh a month in udhaar. Orders and promises arrive as voice notes ("bhaiya 450 ka saman, Shanivar dunga"). The record is a notebook plus a chat scroll:
- **Lost:** 40 voice notes at rush hour; the owner cannot listen to them all.
- **Disputed:** "maine 200 diye the" vs "nahi diye", and nobody can prove either side.
- **Invisible:** a customer who has repaid on time for 5 years has *no credit history*. That is the Invisible City.

## 2. What is new (the unique angle)
Other "WhatsApp bot" or ledger apps make someone **type**. Bolo does three things they don't:
1. **Voice in, any language** (ECHO): Kannada, Hindi, Hinglish, Tamil voice notes. Two speech engines listen; Indian number words ("chaar sau pachaas", "dhai sau", "saade") are normalized.
2. **Never guesses with money:** two people called Ramesh, confusable amounts (₹50 vs ₹15), or engines that disagree always produce a one-tap confirmation card. Machine translation is not allowed to change a number (we caught it inventing a date).
3. **Two-sided, tamper-evident record:** every entry is hash-chained with its original voice note; the *customer* gets it in their language and taps Agree / Dispute / Pay. That agreed history is the asset: a **Khata Passport** the customer can carry to a lender or a new shop.

## 3. Live demo (2 devices, ~2 min)
Setup: laptop shows the **owner console** (`/console/`, Live watch + Khata). A phone (or second laptop) opens **Bolo Chat** at `<tunnel>/chat/`.
1. **Owner speaks** (console → Try it (phone) → Manjunath): voice note "Ramesh chaar sau pachaas ka saman liya, Shanivar dega".
   → Bolo asks *which Ramesh?* (milk-wala or Ramesh Kumar) → card read back in words, due Saturday → ✅ Sahi → text + voice reply.
2. **Customer on a real phone** (Bolo Chat → Lakshmi): "kitna baaki hai" → "aapka total baaki ₹450" + **Pay now** (UPI link with QR) + voice reply.
3. **Customer disputes** by voice: "galat hai, 350 tha" → owner instantly gets Keep / Change buttons. The dispute is a recorded fact, not a fight.
4. **Statement as PDF:** owner says "Lakshmi ka hisaab bhejo" → PDF preview → owner approves → it lands in Lakshmi's chat.
5. **Khata view:** every entry has its audio, who agreed, and an intact hash chain (tamper-evident badge).
Close: "Nobody typed anything. Nobody changed apps. And Lakshmi now has a record that proves she pays."

## 4. Bottlenecks are paperwork, not technology
Show this table when asked "is it live on WhatsApp?":

| Blocker we hit today | What it is | Time to clear with approval |
|---|---|---|
| Twilio trial: replies blocked (21654 / 12300), no templates | Trial-account limit | Upgrade: minutes |
| Meta WhatsApp Cloud API: business portfolio "wait an hour" | New-account cooldown + business verification | 1 hour to 2 days |
| Free-tier AI rate limits (429s, Gemini timeouts) | Free quotas | Paid tier or the local GPU Whisper path already in code |
| Quick tunnel URL changes on restart | Dev tunnel | Fixed domain / deploy |

Proof that the pipe works: real WhatsApp messages from our phone reached the server and were processed (Twilio log + Live watch). The same agent runs behind Bolo Chat, so nothing in the demo is faked; only the last hop to WhatsApp needs an account approval.

## 5. Go-to-market
- **Beachhead:** Bengaluru kiranas with 30–150 credit customers and multilingual customers (Kannada/Hindi/Tamil/English): the language mix is our moat.
- **Distribution:** FMCG distributor salesmen already visit every kirana weekly; they onboard the shop in 2 minutes (owner describes the shop by voice → Bolo configures itself). Distributors want it because the same ledger shows retailer credit.
- **Viral loop:** every customer receives a voice receipt and statement from "Bolo"; the 2nd shop they visit is the next signup.
- **Money:** free for the shop up to 50 customers; ₹199/month above that; **credit-data partnerships** (with consent) with NBFCs and microfinance lenders who pay per verified Khata Passport. That is the big business: underwriting the invisible.
- **Beyond kiranas (same engine, profiles already built):** school fees, clinics, housing-society maintenance, contractors, distributors.

## 6. Judge Q&A (short answers)
- **Why not Khatabook/OkCredit?** They need typing by the owner and nothing from the customer. Bolo takes the voice note that already exists, and the customer confirms. That turns a private notebook into evidence.
- **What if speech gets it wrong?** It never commits money on a guess: confirmation card, two engines, number read back in words, corrections by voice ("nahi, 540"), undo as a reversal row.
- **Privacy?** Customer data stays with the shop. Credit sharing is opt-in per customer, and only agreed entries count.
- **Why will owners pay?** Fewer disputes and faster collection: the reminder + Pay-now link recovers dues that a notebook forgets.
- **What was hard?** Indian number words and fractions, two people with the same name, translations that changed numbers, provider trial limits.
- **What would you do next week?** Meta business verification for production WhatsApp, a 10-shop pilot in Jayanagar, and Khata Passport sharing with one NBFC partner.
