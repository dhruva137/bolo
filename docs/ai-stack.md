# Speech and model setup

## Zero-cost demo

Leave the API keys in `.env` blank. From `backend/`, install `requirements.txt` and run the setup command once while connected to the internet.

```powershell
python -m voice.setup
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

The installer downloads the multilingual Whisper tiny weights and verifies the model checksum. The model lives under `data/models/whisper-tiny` and is excluded from Git. `BOLO_STT_MODEL` can point to a prepared local CTranslate2 model directory. On another laptop, rerun setup after cloning. [Whisper tiny weights](https://huggingface.co/Systran/faster-whisper-tiny)

In the console, load the kirana shop, choose a speaker in the phone simulator and tap the microphone. Tap again to send. The backend keeps the original recording, converts a copy to mono 16 kHz PCM with FFmpeg and transcribes it with faster-whisper. Inference uses CPU int8, one thread and one worker. The rule planner checks the transcript against the shop. The text and confirmation buttons remain visible while eSpeak NG produces the spoken reply. The local voice uses the reply text as written, so mixed-language base copy may still sound Hinglish. General translation and invoice OCR require a configured provider. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [eSpeak NG](https://github.com/espeak-ng/espeak-ng)

## Optional free-tier keys

| Key | Enables | Free usage |
|---|---|---|
| `GROQ_API_KEY` | Whisper large-v3-turbo transcription and GPT-OSS 120B planning | Use the free plan within its model-specific request and audio limits. [Groq limits](https://console.groq.com/docs/rate-limits) |
| `GEMINI_API_KEY` | Gemini 3.8 Flash planning and audio fallback | Standard input and output have a free tier with quotas. Free-tier data can be used to improve Google products. [Google pricing](https://aistudio.google.com/docs/pricing#gemini-3.8-flash) |

Both keys can stay blank throughout the simulator demo. For optional WhatsApp test-number configuration, see [WhatsApp setup](setup-whatsapp.md).

## Optional metered integrations

Keep `SARVAM_API_KEY` blank for the zero-cost build. Sarvam provides introductory credits and then meters consumption. The adapters support Saaras v4 STT, Bulbul v3 speech synthesis, Mayura translation, Sarvam 105B planning and Document AI OCR. Bolna call escalation is also optional and disabled with blank credentials. [Sarvam pricing](https://www.sarvam.ai/api-pricing) · [Bolna calls](https://www.bolna.ai/docs/api-reference/calls/make)

## Provider behavior

- Sarvam receives up to 50 keyterms in one JSON-encoded multipart field, alongside the WAV file, codemix mode and automatic language detection. The short API path splits long notes into segments of at most 30 seconds and rejoins each engine's results in order. An engine that fails on one segment cannot authorize a partial transaction. [Sarvam speech API](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe)
- Groq returns a verbose Whisper transcript. With both primary speech providers configured, they run independently. Gemini can supply a missing transcript. If all configured cloud engines fail, the installed local model can still transcribe the note. Each stored inbound message identifies the engine that produced the usable text. [Groq speech](https://console.groq.com/docs/speech-to-text) · [Gemini audio](https://aistudio.google.com/docs/audio)
- The planner asks the first configured model in `LLM_ORDER` for JSON. Invalid output or a provider failure falls through to the next configured model and finally to the offline rules. The default order is Gemini, Sarvam and Groq.
- Bulbul v3 returns base64-encoded MP3. FFmpeg converts it to mono OGG/Opus. A Bulbul failure can fall back to bundled eSpeak NG. Mayura translation handles blocks up to 1,000 characters and leaves the original text available when translation fails. [Bulbul](https://docs.sarvam.ai/api-reference/text-to-speech/convert) · [Mayura](https://docs.sarvam.ai/api-reference/text/translate-text)
- Document AI accepts a PDF or zipped page image, returns a job ID and serves a Markdown archive when processing finishes. The client stops polling on timeout or failure. [Document AI](https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/how-to/parse)
- Provider requests use finite timeouts. Read and inference requests can retry once after a transient failure. External sends, calls and document-job creation retry on a failed connection or explicit rate limit.
