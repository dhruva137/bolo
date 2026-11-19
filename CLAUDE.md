# Bolo: engineering guide (for humans and AI assistants)

Bolo is a WhatsApp voice-note operations agent for small businesses, starting with the kirana khata. The owner talks; Bolo listens, cleans the audio, hears it with two speech engines, normalizes Indian numbers and names, plans tool calls, double-checks anything risky, acts (ledger, polls, tasks, documents, reminders), and follows up with people in their own language.

Read first: `README.md` → `docs/agent.md` → `docs/architecture.md` → this file.

## Run

From the repository root on Windows, run `.\scripts\start-demo.ps1`. It installs the speech model on first use, sets `BOLO_OFFLINE=1` and serves the owner console on loopback. Choose **Kirana demo → Open phone simulator**. A local voice note opens a transcript review before the planner runs. A reviewed money action still requires the applicable confirmation.

From `backend/`, run `python -m tests.test_flow` to exercise all 21 tools. Backend unit tests live in `tests/`; the browser regression lives in `frontend/tests/test_console.py`.

## Code map (backend/)
| File | Responsibility |
|---|---|
| `app.py` | FastAPI: WhatsApp webhook, console API, simulator endpoints, `/pay`, files, scheduler loop |
| `config.py` | env keys; every key optional; `status()` shows what's live |
| `db.py` | SQLite schema + helpers + settings + audit log |
| `brain/agent.py` | **the agent**: inbound handling, money verification cards, corrections, customer loop, approvals, every tool, scheduler `tick()` |
| `brain/planner.py` | transcript → tool calls (LLM with shop context; offline rule planner fallback) |
| `brain/llm.py` | Gemini / Sarvam / Groq JSON calls with fallback order `LLM_ORDER` |
| `brain/normalize.py` | Indian number words, fractions (dedh, dhai, sawa, paune, saade), confusable amounts, dates |
| `core/ledger.py` | append-only hash-chained ledger, reversals, balances, `verify_chain()` |
| `core/contacts.py` | contacts, roles, cross-script name matching (romanize + rapidfuzz), disambiguation |
| `core/access.py` | role permissions and owner-approval rules |
| `features/profiles.py` | business types (kirana, school, clinic, D2C, distributor, contractor, society, generic): role names, dues word, feature packs, onboarding from the owner's own description, feature toggles |
| `features/knowledge.py` | knowledge base: files to share by role + facts the bot answers from |
| `features/polls.py` | smart polls and tasks: per-person buttons, tally, nudges, call escalation |
| `features/documents.py` | HTML templates → PDF via headless Edge/Chrome |
| `voice/audio.py` | ffmpeg denoise; TTS → WhatsApp OGG/Opus voice note |
| `voice/stt.py` | Sarvam Saaras v4 (keyterms) + Groq Whisper, in parallel |
| `voice/tts.py`, `voice/translate.py`, `voice/docai.py` | Sarvam Bulbul, Mayura, Document AI |
| `pipe/whatsapp.py` | WhatsApp Cloud API (v27.0) send/receive/media |
| `pipe/messenger.py` | the only way to message people: stores, translates, speaks, sends |
| `pipe/calls.py` | Bolna outbound call escalation |
| `seed.py` | demo shop (two Rameshes, delivery team, supplier, partner, 35-day overdue) |

Frontend (`frontend/`): vanilla HTML/CSS/JS owner console served at `/console/`, no build step. Views: onboarding, dashboard, live watch (pause bot / take over chat / reply as business), phone simulator, khata, polls, approvals, people & roles, products, features, knowledge, templates, settings, activity.

Watch mode: `bot_mode=paused` (whole bot) or `contacts.paused=1` (one chat) → inbound is still stored and transcribed, but the agent doesn't reply.

## Button ids (WhatsApp interactive replies)
`ok|fix|redo:<pending>` · `pick:<pending>:<item>:<contact>` · `new:<pending>:<item>` · `num:<pending>:<item>:<value>` · `poll:<poll>:<option>` · `agree|dispute|pay:<ledger>` · `keep|change:<claim>` · `recv|norecv:<ledger>` · `approve|reject:<approval>` · `media:<message>:template|supplier|ignore`

## Rules of the codebase
- Ledger money rows are never updated or deleted. Corrections are reversal rows plus a new row. Status (agreed/disputed/claimed) is metadata outside the hash.
- Read current status from the SQLite view `ledger_current`. Each change appends to `ledger_status`. Starting a fresh shop returns an archive prefix such as `archive_20261119T085500123456Z`. In a read-only SQLite session on `data/bolo.db`, inspect `<prefix>_ledger`, `<prefix>_ledger_status`, `<prefix>_contacts` and `<prefix>_events` together. Their IDs and audio references still match.
- Every outgoing message goes through `pipe/messenger.py` (storage, translation, voice, WhatsApp).
- Money is never committed silently on a guess: ambiguous names, engine disagreement, confusable amounts and low confidence always produce a confirmation card.
- New tools: add to `planner.OWNER_TOOLS`/`CUSTOMER_TOOLS`, implement `t_<tool>` in `agent.py`, register in `TOOLS`, add permissions in `core/access.py`, add a case to `tests/test_flow.py`.
- Every new library, API, model or generator gets a line in `DECLARATIONS.md` in the same commit.
- Keep code explainable by every team member; comment the non-obvious parts.
