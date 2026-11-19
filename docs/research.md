# Research and related work

## Model choices
| Hop | Primary | Fallbacks | Why |
|---|---|---|---|
| Speech-to-text | Sarvam `saaras:v4` in `codemix` mode with automatic language ID and **`keyterms` set to the shop's own catalog and customer names** (22 Indian languages + English; accepts WhatsApp OGG/Opus directly) | Groq `whisper-large-v3-turbo`; Gemini Flash audio | Sarvam's Saaras v3 is reported among the top systems on the *Voice of India* real-world benchmark ([summary](https://tldr.takara.ai/p/2604.19151)); Whisper keeps us running offline and under rate limits |
| Understanding | Gemini Flash with `response_schema`, grounded on the shop's catalog and customers, after a rule-based Indic quantity normalizer | Groq-hosted open models in JSON mode; replies written by Sarvam `sarvam-105b` | extraction without per-language training data, in the spirit of LLM-based multilingual SLU ([arXiv 2404.02588](https://arxiv.org/pdf/2404.02588.pdf)) |
| Text-to-speech | Sarvam `bulbul:v4-flash` / `bulbul:v3` (kn, hi, ta, te and more), transcoded to Opus so it arrives as a native voice note | Gemini TTS; browser speech synthesis | the reply must be audible in the speaker's language |
| Translation | `sarvam-translate:v1` (22 languages) and `mayura:v1` (colloquial / code-mixed modes) | — | each party reads the same order in their own language |
| Documents | Sarvam Vision Document AI (Parse + Extract on photos/PDFs of invoices, 23 languages); Sarvam document translation for statements | — | an invoice photo becomes stock-in + amount payable, not just an explanation |
| Channel | WhatsApp Cloud API (test number + webhook; Twilio WhatsApp sandbox as backup) ([docs](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [audio messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/audio-messages)) | Bolo web app: record, or share a voice note to it | official API only |

Open-weight alternatives we evaluated for self-hosting:
- **SraVaani-1.0** (IISc/ARTPARK, 2026): open Indic ASR covering 65 Indian languages and dialects ([paper page](https://huggingface.co/papers/2608.08235)).
- **Whisper-Hindi2Hinglish** (Oriserve): Whisper fine-tuned on noisy Indian-accented Hindi ([post](https://oriserve.com/blog/oriserve-open-sources-india-focused-ai-speech-model-fine-tuned-on-whisper)).
- **Indic Parler-TTS** (AI4Bharat): open TTS for 21 Indian languages, with the voice controlled by a text description ([model](https://huggingface.co/ai4bharat/indic-parler-tts), [paper](https://arxiv.org/html/2505.18609v1)).

## Design principles from research
| Principle | Evidence |
|---|---|
| Voice in, voice out, in the user's language and code-mix | WhatsApp voice notes are a primary channel for people who struggle to type their script: Reitmaier et al., *Opportunities and Challenges of ASR Systems for Low-Resource Language Speakers*, CHI 2022 ([link](https://cronfa.swansea.ac.uk/Record/cronfa59573)); Medhi et al., *Designing Mobile Interfaces for Novice and Low-Literacy Users*, TOCHI 2011 ([pdf](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ToCHI2711_Medhi.pdf)) |
| Read back and confirm before money; offer a tap fallback | confirmation prompts reduced multi-digit errors (Chakraborty et al., DEV 2013, [pdf](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/Chakraborty-dev2013-ivr.pdf)); first-time users preferred keypad input for critical entries (Patel et al., *Avaaj Otalo*, CHI 2010, [pdf](https://hci.stanford.edu/publications/2010/p50-patel.pdf)) |
| Deterministic number normalization after ASR | rule-based inverse text normalization for 11 Indic languages ([arXiv 2203.16825](https://arxiv.org/abs/2203.16825)) |
| Show the document and say its meaning; confirm extracted fields | Indic OCR lags English (IndicVisionBench, [arXiv 2511.04727](https://arxiv.org/abs/2511.04727)); IndicTrans2 for Indic translation ([arXiv 2305.16307](https://arxiv.org/abs/2305.16307)) |
| Zero cost, no new app, a human in the loop | CGNet Swara (Mudliar et al., ICTD 2012, [pdf](https://billthies.net/assets/pdf/swara-ictd12.pdf)); Mobile Vaani (Moitra et al., ICTD 2016) |
| Test on real, code-mixed Indian speech | IndicVoices ([arXiv 2403.01926](https://arxiv.org/abs/2403.01926)), Vistaar ([arXiv 2305.15386](https://arxiv.org/abs/2305.15386)), LAHAJA ([arXiv 2408.11440](https://arxiv.org/abs/2408.11440)) |

## Related work
| System | What it does | How Bolo differs |
|---|---|---|
| **Jugalbandi** (Microsoft Research, AI4Bharat, OpenNyAI) ([story](https://news.microsoft.com/source/asia/features/with-help-from-next-generation-ai-indian-villagers-gain-easier-access-to-government-services/), [repo](https://github.com/OpenNyAI/Jugalbandi-Manager)) | WhatsApp voice → Indic ASR → translation → LLM → spoken answer about government schemes | Jugalbandi *answers questions*; Bolo *creates confirmed transactions* in a system of record, with audio-backed proof |
| Digital khata apps (Khatabook, OkCredit, Vyapar) | credit ledgers the owner types into | Bolo needs no typing, the customer takes part, and every entry has voice evidence |
| WhatsApp → Whisper → LLM auto-reply templates (e.g. [n8n](https://n8n.io/workflows/16897)) | generic transcribe-and-reply | ungrounded and stateless; Bolo grounds on the shop's catalog and customers, gates on confidence, and keeps a ledger |
| ONDC / DigiDukaan ([explainer](https://commmerce.com/blog/ondc-digidukaan-b2b-procurement-kirana-stores/)) | B2B procurement for kiranas | complementary; Bolo's distributor reorder-by-voice could feed it |

## Code-mixing
Indian voice notes routinely mix languages inside a sentence. Datasets such as COMI-LINGUA ([arXiv 2503.21670](https://arxiv.org/html/2503.21670v2)) show how common Hindi–English mixing is. Bolo handles mixing at three points: the ASR model (trained on code-mixed speech), the extractor prompt (accepts mixed input), and the validator (romanised alias matching).

## What we measure
The metric is **action accuracy**, not word error rate. What matters is whether the right customer, items, quantities, amount and payment type reached the system. On our recorded voice-note set (several languages, shop background noise) we compare:
- **Baseline:** transcript + keyword rules
- **Bolo:** transcript → grounded extraction → confidence gate (read-back corrections counted)

We report per-field F1, the share of notes auto-committed, the correction rate after read-back, and median latency. Results: [`../eval/`](../eval/).

## Market context
- About 13M kirana stores in India, roughly 1.4M digitised (AICPDF figure, via [commmerce.com](https://commmerce.com/state-of-indian-multi-store-retail/)). Just over 90% of FMCG sales go through kiranas ([Cornell](https://business.cornell.edu/article/2026/05/indias-digital-pull-revolution/)).
- A common setup is a billing machine, a paper register for credit, and a WhatsApp group for delivery orders ([commmerce.com](https://commmerce.com/blog/how-indian-kirana-stores-go-omnichannel-without-losing-walk-in-customers/)).
- WhatsApp users send 7 billion voice messages a day globally (2022, [TechCrunch](https://techcrunch.com/2022/03/30/people-are-sending-7-billion-voice-messages-on-whatsapp-every-day)).
