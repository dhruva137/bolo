# Demo cheat sheet (copy a line, or say it into the mic)

Two windows, one chat each: **business** at `http://localhost:8002` (log in as the shop) and **customer** at `http://localhost:8001` (tap Lakshmi). Speak the line, or paste it if the room is noisy. Names, items and amounts can be changed freely; nothing is hard-coded.

## Owner (business side → Assistant chat)
| # | Say | What happens |
|---|---|---|
| 1 | `Ramesh chaar sau pachaas ka saman liya, Shanivar dega` | Which Ramesh? → confirm card → khata entry with audio |
| 2 | `Tomato ka rate ab 40 ho gaya, sabko bata do` | Price list updated; every customer told in their language |
| 3 | `Yaad rakh: kal Sunday dukaan 2 baje band rahegi` | Saved; customers asking about timings get this answer |
| 4 | `Delivery team se pucho Saturday 5 baje stock count, kaun aa raha hai` | Ravi and Imran asked privately with buttons; tally to owner |
| 5 | `Kaun kaun ka kitna baaki hai` | Everyone's dues, oldest first |
| 6 | `Aaj ka hisaab` | End-of-day summary |

## Customer (customer side → shop chat)
| # | Say | What happens |
|---|---|---|
| 7 | `Bhaiya do packet atta aur ek Fortune oil bhej do` | Priced order (₹…) → ✅ Confirm / ✏️ Change / 💬 Other → owner gets the ticket |
| 8 | `Mera bill bhej do, payment karna hai` | PDF statement + 💸 Pay now (UPI) sent to the customer; owner informed |
| 9 | `Tomato aaj kitne ka hai?` | Answer from the owner's own price list |
| 10 | `Galat hai, 350 tha` | Dispute → owner gets Keep / Change with the original voice note |
| 11 | `Maine do sau rupay GPay kar diye` | Payment claim → owner gets ✅ Mila / ❌ Nahi mila |
| 12 | `Hi, how much is the Fortune oil today? Do you deliver?` (as a new person) | English customer gets English answers from the shop's data |

## Order for a 3-minute video
1 → 7 (Confirm) → owner taps 📒 Udhaar → 8 → 10 → 2 → 12. Each reply takes 6–15 s; trim the waits in editing.
