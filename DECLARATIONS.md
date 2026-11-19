# Declarations

Everything in this repository was built by Team Axon on 19 Nov 2026, inside the Rewired build window. Third-party resources:

## AI tools
| Tool | Used for |
|---|---|
| Claude Code (Anthropic) | research, documentation drafts, code assistance (used by Dhruva P Gowda) |
| OpenAI Codex and its coding subagents (OpenAI) | Continuation build, code review, implementation and test automation |

## Models and APIs
| Name | Purpose |
|---|---|
| Sarvam `saaras:v4` | speech-to-text (Indic, code-mixed) |
| Sarvam `bulbul:v3` | text-to-speech replies |
| Sarvam `sarvam-105b`, `mayura:v1`, Document AI | agent, translation, invoice reading |
| Groq `whisper-large-v3-turbo` and `openai/gpt-oss-120b` | Optional hosted speech recognition and JSON planner |
| OpenAI Whisper tiny, Systran CTranslate2 conversion (MIT) | Offline multilingual speech recognition on one CPU thread |
| Bolna outbound call API | Optional configured phone escalation |
| Google `gemini-3.8-flash` | fallback agent model |
| Meta WhatsApp Cloud API (v27.0), Twilio WhatsApp sandbox | messaging |

## Libraries and frameworks
| Name | Version | Purpose |
|---|---|---|
| FastAPI, uvicorn, httpx, python-dotenv, python-multipart | latest | backend, HTTP |
| rapidfuzz, indic-transliteration | latest | name/product matching across scripts |
| qrcode, pillow | latest | UPI QR on the pay page |
| Microsoft Edge / Chrome (headless) | system | HTML → PDF rendering |
| ReportLab | 4.4.x | Local PDFs for the standard Latin-script shop templates |
| google-genai, openai (client for Sarvam's OpenAI-compatible API) | latest | LLM clients |
| FFmpeg and imageio-ffmpeg | FFmpeg 9.0.2 in imageio-ffmpeg 0.8.1 | Audio cleaning and OGG/Opus encoding |
| eSpeak NG and espeakng-loader | Loader 0.2.4 | Bundled offline voices for spoken replies and synthetic evaluation input |
| faster-whisper and CTranslate2 | 1.2.1 and 4.9.0 | Run Whisper on CPU with int8 weights |
| PyAV, NumPy, ONNX Runtime, tokenizers, huggingface-hub | faster-whisper dependencies | Audio decoding and local speech runtime |
| cloudflared | latest | public tunnel for the webhook |
| Microsoft Playwright for Python, headless Google Chrome | 1.65.2 / system | Desktop and mobile browser regression tests |
| Git and PowerShell | system | Version control, sanitized snapshots and tag verification |

## Templates, generators, UI kits
| Name | Notes |
|---|---|

## Data
| Source | Notes |
|---|---|
| Synthetic speech and shop messages | Offline regression fixtures created from fictional transactions. Human-speaker recordings were unavailable. |
| Synthetic shop catalog and customers | demo seed data |

## Installed Python dependency versions

Windows build inventory for the packages required by `backend/requirements.txt`, including their installed dependencies. Runtime also uses Python’s standard library and SQLite. Browser QA uses Playwright with its greenlet transport dependency.

- `annotated-doc 0.0.7`, `annotated-types 0.8.0`, `anyio 4.16.0`, `av 19.0.2`, `backports.functools-lru-cache 2.0.0`
- `certifi 2026.10.23`, `cffi 2.1.1`, `charset-normalizer 3.5.2`, `click 8.5.1`, `colorama 0.4.6`
- `cryptography 50.0.2`, `ctranslate2 4.9.0`, `distro 1.9.0`, `espeakng-loader 0.2.4`, `fastapi 0.165.0`
- `faster-whisper 1.2.1`, `filelock 4.2.12`, `flatbuffers 25.12.19`, `fsspec 2026.9.0`, `google-auth 2.62.2`
- `google-genai 3.6.1`, `h11 0.16.0`, `hf-xet 1.8.0`, `httpcore 1.0.9`, `httpcore2 2.16.2`
- `httptools 0.9.0`, `httpx 0.28.1`, `httpx2 2.16.2`, `huggingface_hub 2.4.0`, `idna 3.20`
- `imageio-ffmpeg 0.8.1`, `indic_transliteration 2.3.82`, `jiter 0.19.0`, `markdown-it-py 4.3.0`, `mdurl 0.1.2`
- `numpy 2.5.5`, `onnxruntime 1.32.0`, `openai 3.55.1`, `opentelemetry-api 1.45.2`, `packaging 26.3`
- `pillow 13.0.0`, `protobuf 7.36.2`, `pyasn1 0.6.5`, `pyasn1_modules 0.4.2`, `pycparser 3.12`
- `pydantic 2.14.3`, `pydantic_core 2.50.4`, `Pygments 2.21.0`, `python-dotenv 1.2.4`, `python-multipart 0.0.34`
- `PyYAML 6.0.3`, `qrcode 8.2`, `RapidFuzz 3.14.6`, `regex 2026.11.19`, `reportlab 4.4.10`
- `requests 2.34.2`, `rich 15.0.0`, `roman 5.2`, `shellingham 1.5.4`, `sniffio 1.3.1`
- `starlette 1.10.0`, `tenacity 9.1.4`, `tokenizers 0.23.3`, `toml 0.10.2`, `tqdm 4.70.1`
- `truststore 0.10.5`, `typer 0.29.2`, `typing-inspection 0.4.5`, `typing_extensions 4.16.0`, `urllib3 2.8.0`
- `uvicorn 0.54.0`, `watchfiles 1.3.0`, `websockets 17.4`

### Container (added 19 Nov, build window)
- Docker image `python:3.12-slim` (Debian) with apt packages `ffmpeg`, `chromium`, `fonts-noto-core`, `fonts-noto-color-emoji`; `Dockerfile` and `docker-compose.yml` written with Claude Code (Claude Opus 5.5).
- WhatsApp-style simulator styling (CSS/JS look-alike, no WhatsApp artwork), Twilio TwiML reply path, translation number guard and offline "hisaab bhejo" rule written with Claude Code (Claude Opus 5.5).
- Landing page `product-demo/` by Prem (Team Axon); its hero photo `shopkeeper.png` was generated with a built-in image generator (prompt recorded in `product-demo/index.html`). "Try it live" section, three-port launcher (`backend/serve.py`), business portal with live chat logs, voice orders priced from the catalog, and `docs/demo-stories.md` written with Claude Code (Claude Opus 5.5).
