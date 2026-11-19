# Bolo: product design

Design rule: **nobody changes behaviour.** Customers keep sending voice notes, shopkeepers keep talking, and the system adapts to them. Every layer below either removes a WhatsApp failure or creates a reason for the next person to join.

## 1. Layers of use

### L1 Customer (the talker). Direct.
| Says (any language, mixed is fine) | Bolo does |
|---|---|
| "2 kilo atta, ek Fortune oil bhej do" | order ticket + spoken read-back + ETA |
| "Udhaar mein likh lo" / "account-alli haaki" | credit entry with the voice note attached |
| "Kitna baaki hai?" | spoken balance + last 3 entries |
| "Maine 500 GPay kiya" | payment entry marked *claimed*; owner confirms with one tap or one voice note |
| "Kal wala order cancel" | cancels the latest open order, confirmed by voice |
| "Same as last week" | repeats the last order, confirmed by voice |
Details: replies use the customer's language and name, numbers are spoken naturally ("teen sau athaara"), it remembers each person's usual brand ("Fortune, like last time?"), and family members can order on one household account.

### L2 Shop owner. Direct.
- **Queue, not scroll:** live tickets (new → packing → ready → delivered), each with a play button for the original note.
- **Pick-list:** today's open orders, grouped by item, so one walk down the shelves serves many tickets.
- **Ledger:** balance per customer, how old the dues are (0–7 / 8–30 / 30+ days), and the full audio trail.
- **Talk to it:** "Ramesh ne 300 diye", "Lakshmi ka order ready", "Aaj ka hisaab batao".
- **9 pm voice summary:** "Today: 42 orders, ₹3,200 given on credit, ₹1,800 recovered, 3 customers past 30 days."
- **Remind all:** one tap sends polite voice reminders in each customer's language, and the owner never has to make the awkward ask.
- **Missed-demand radar:** "5 people asked for Amul Taaza today, and it's out of stock" (counted from the orders).
- **"WhatsApp would have lost these":** a counter of notes that came in during rush hour or overnight and were all captured. This is the proof-of-breakage metric, live.

### L3 Staff / delivery. Direct.
"Ramesh ka order de diya" → delivered, with the time recorded. "Lakshmi ghar pe nahi" → flagged for the owner.

### L4 Distributor / supplier. Indirect.
- The owner says "Distributor ko bolo 10 Fortune, 5 atta" → a structured purchase order, sent as a message *and* a voice note.
- Aggregated (opt-in, anonymised) demand across shops lets distributors restock before a shop runs out.

### L5 Lender / credit. Indirect, roadmap.
A shop's ledger of credit given and recovered becomes a cash-flow record. With the owner's explicit consent, it can support a small working-capital loan. The customer side can earn a "good payer" record that travels with them.

### L6 City. Indirect. This is the theme.
Informal credit is one of the city's biggest invisible economies: it is spoken, never written, and never counted. Bolo turns it into **anonymised, aggregated** numbers by neighbourhood: credit extended, recovery rate, essentials demand. That can feed food-security and microfinance planning. **Heard** (voice in any language), **counted** (credit and demand), **said** (needs voiced, not typed).

## 2. Why people adopt it, and keep using it

**Zero onboarding**
- The shop forwards *one* existing voice note to Bolo. In 60 seconds it sees a ticket. That is the "aha".
- The catalog bootstraps itself: start with ~40 common SKUs, then learn from every order. New spoken aliases ("Fortune wala tel", "sunflower ennai") are added after the owner confirms once.
- The customer list builds itself from names spoken in the notes and the sender number.

**Habit loops**
- The owner gets a daily 9 pm summary voice note and a weekly "₹ recovered because of Bolo" figure.
- The customer gets an instant spoken receipt and a balance whenever they ask.

**Growth loops (why it spreads)**
1. **Receipt loop:** every voice receipt ends with a 2-second sign-off, "Bolo se". Customers hear it, so customers at other shops ask for it.
2. **Passbook loop (network effect):** a customer who buys on credit at 3 shops gets **one spoken passbook across all of them** ("You owe ₹450 at Sri Ganesh Stores and ₹120 at Ravi Medicals"). The more shops on Bolo, the more useful it is to each customer, so customers pull their other shops in.
3. **Distributor loop:** a distributor's salesman sees reorders arriving as clean POs and onboards the next shops on their beat, because it makes his route faster.
4. **Association loop:** traders' WhatsApp groups get a monthly "credit recovered" leaderboard (opt-in).
5. **Referral:** a shop that brings in a shop gets a free month.

**Trust (or nobody uses it for money)**
- Low-confidence money is never committed silently. It is always read back first.
- Each credit entry is hash-chained with the audio's fingerprint, so edits are visible and the original is playable.
- Payments the customer claims ("I paid") stay *claimed* until the owner confirms them.
- The first reply includes a consent line. Customers can ask to "delete my voice notes". Audio stays within the shop's account.
- There are caps: credit above a threshold always needs the owner's confirmation.

## 3. Scope for today (the 7-hour cut)
| Priority | Feature |
|---|---|
| **Must** (demo dies without it) | voice in (upload/record + WhatsApp if the API works) → STT → grounded extraction → read-back gate → order queue + ledger with audio + hash; voice reply; shop console |
| **Should** (wow) | dispute playback; remind-all; "kitna baaki"; multilingual demo (kn/hi/en/Hinglish); evaluation numbers; "WhatsApp would have lost these" counter |
| **Could** | 9 pm summary; missed-demand radar; staff "delivered"; distributor PO |
| **Roadmap** | cross-shop passbook, lender layer, city-level anonymised insight, domestic-worker and water-tanker versions on the same engine |

## 4. Success metrics
Time to first ticket (< 60 s) · % of notes auto-committed · correction rate after read-back · ₹ credit recovered per shop per month · weekly active shops · notes per shop per day · day-30 retention · K-factor from the receipt and passbook loops.

## 5. The core primitive: two-sided voice consent
Every credit entry starts as one person's voice note and becomes **binding only when the other side agrees by voice**: "haan" (Hindi), "howdu" (Kannada), "aamam" (Tamil), "avunu" (Telugu), "yes". Both clips are stored with the entry and hashed into the ledger. Digital khata apps have the owner type, and the customer never agrees to anything. In Bolo, a dispute ends by playing the customer's own "howdu".

The same primitive works beyond kiranas. A domestic worker's wages and leave, a contractor's daily muster, and a tanker delivery are all promises made by voice that nobody records. Karnataka's draft Domestic Workers Bill (2025) explicitly asks for an employment record beyond a "WhatsApp promise".

## 6. Multilingual by design
- **Language mirroring:** the reply comes back in the language the person spoke (Kannada, Hindi, Tamil, Telugu, English), including Hindi-English code-mix.
- **Code-mixed transcripts:** English words stay in Latin script and Indic words in native script, as people actually talk in shops.
- **Spoken quantities:** dedh (1.5), dhai (2.5), sawa (+¼), paune (−¼), aadha/ardha (½), "dedh sau" (150), ondu-vare (1.5) and equivalents are normalized before understanding.
- **Cross-script products:** "tamatar", "ಟೊಮೆಟೊ", "टमाटर" and "tomato" all resolve to the same item.
- **Consent words** are recognized in every supported language.

## 7. The whole chain, in everyone's language
A kirana's day is a chain of people who often share no language: a Hindi-speaking migrant customer, a Kannada-speaking owner, an Odia-speaking delivery boy, an English-invoicing distributor. Bolo lets every one of them talk in their own language:
| Link | Voice in | Optional context | Becomes | Out |
|---|---|---|---|---|
| Customer → shop | order / "khate mein likho" | photo of an empty packet | order + pending credit | read-back voice + ✅/❌; consent recorded |
| Shop → delivery boy | "Lakshmi ka order, 3rd cross" | location pin | delivery task | voice in the delivery boy's language; "de diya" → delivered |
| Customer asks | "kitna baaki?" / "bill samjhao" | — | ledger query | voice answer + itemized statement PDF in the customer's language |
| Distributor invoice | owner: "is bill mein kya hai, sahi hai?" | photo of the invoice | parsed invoice → stock-in + payable, mismatches flagged | voice explanation in the owner's language |
| Shop → distributor | "10 Fortune, 5 atta bhejo" | — | purchase order | PO PDF in the distributor's language |
| Owner → all | "sabko yaad dilao" | — | reminders | each customer reminded in their own language |
The voice note is always the way in. Photos and PDFs are context that makes the action more precise. They never replace the voice.

## 8. Beyond the khata: the owner talks, Bolo follows through
The khata is where Bolo starts. The same agent runs a small business's everyday follow-through from voice notes:
| Owner says | Bolo does |
|---|---|
| "Saturday 5 baje stock count, Ravi Suresh Imran aana hai, kaun aa raha hai pucho" | asks each person in their language with [Haan] [Nahi] [Late] buttons, tallies the answers live, reminds anyone who hasn't replied, escalates to a phone call, reports "Ravi ✅ Suresh ❌ Imran ⏰" |
| "Sharma ji ko quotation bhejo, 50 bag cement 380 ke rate se" | fills the shop's own saved quotation template, shows the owner a PDF preview, sends on approval |
| "Partners ko aaj ka hisaab bhejo" | day-summary PDF to the partners list |
| "Delivery team ko bolo Jayanagar wale pehle" | task to each delivery person in their language with a [Done] button |

**Templates:** the owner sends a photo or PDF of their existing bill, quotation or challan once. Sarvam Vision parses it into a reusable template, and later voice notes fill it.

**Controlled access:** owner, staff, partners, delivery team, suppliers and customers each see and do only what their role allows. Anything sent to many people, any document going to an outside party, and any large amount waits for the owner's approval. Every action is in an audit log with the original audio.

**Smart polls instead of group polls:** the official WhatsApp API doesn't support polls and limits bot-managed groups to 8 people. Bolo asks each person individually with buttons. That's more useful than a group poll: every answer is attributed, each person is asked in their own language, and non-responders are followed up privately.
