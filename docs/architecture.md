# Bolo architecture

Bolo serves a vanilla JavaScript owner console and a FastAPI application backed by one SQLite shop database. The local simulator drives the same agent that handles WhatsApp. The display polls the console API for new messages.

## From a voice note to a ledger entry

1. The simulator sends a multipart upload to `POST /api/simulate/audio`. The agent stores the original recording and its SHA-256 digest. FFmpeg decodes and cleans the audio to 16 kHz mono PCM.
2. With all keys blank, faster-whisper runs the local multilingual tiny model on a single CPU thread. The simulator shows the engine transcript and lets the sender replay the note, correct it or discard it. Accepting a transcript reuses the original audio digest. The original engine text remains available.
3. `brain/planner.py` normalizes number words and proposes tool calls using a shop-specific rule planner. When configured, hosted planners run first. The agent checks the speaker’s role and resolves names against the shop contacts.
4. Money entries pass through read-back, name disambiguation and confirmation. The ledger hashes each row with the preceding hash. A correction appends a reversal and a replacement. Customer agreement, dispute and payment decisions are separate status records.
5. Outbound text, buttons, files and speech go through `pipe/messenger.py`. eSpeak NG and FFmpeg produce OGG/Opus locally. Per-person preferences control voice replies. Free-form language translation uses the optional configured provider.

## Console and transport boundaries

| Entry point | Use |
|---|---|
| `GET /console/` | Local owner console |
| `POST /api/simulate` | Text and button actions in the simulator |
| `POST /api/simulate/review` | Accept or discard a simulator transcription |
| `GET /api/messages` | Messages for a selected phone since a given cursor |
| `GET /api/live/threads` | Conversations, last inbound gist and explicit wording flags |
| `GET /api/ledger` | Balances, entries and chain verification |
| `GET /api/polls` and `GET /api/approvals` | Poll tallies and owner decisions |
| `POST /webhook` and `POST /twilio` | Official messaging callbacks on the dedicated gateway |

The public gateway accepts provider callbacks and limited shared-resource URLs. Its durable inbox uses the provider message ID to handle redelivery. Ambiguous failures after a side effect require reconciliation. The owner console runs on loopback. See [WhatsApp setup](setup-whatsapp.md).

## Verification

The offline flow suite posts through the application and checks financial outcomes, permissions, PDFs and the delivery tally. Browser tests cover both desktop and phone layouts. Transport tests use signed fixtures. The evaluation directory contains each synthetic note, its reference fields and a scorer. See the [evaluation and results](../README.md#evaluation).
