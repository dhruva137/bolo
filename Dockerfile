# Bolo in one container: landing page (8000), customer chat (8001), business portal (8002), one shared agent.
# Default: key-free offline mode (local Whisper + eSpeak NG). Pass API keys to switch to cloud speech/AI.
FROM python:3.12-slim

# ffmpeg: audio cleanup and OGG/Opus voice notes. chromium: HTML -> PDF bills and statements. fonts: Indic scripts in PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg chromium fonts-noto-core fonts-noto-color-emoji ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend
COPY chat chat
COPY product-demo product-demo

# Speech model lives outside the data volume so a fresh volume still has it.
ENV BOLO_STT_MODEL=/opt/models/whisper-tiny \
    BOLO_DATA_DIR=/app/data \
    BOLO_OFFLINE=1 BOLO_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
WORKDIR /app/backend
RUN python -m voice.setup

# 8000 landing + dashboard + API · 8001 customer chat · 8002 business portal
EXPOSE 8000 8001 8002
VOLUME ["/app/data"]
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["python", "serve.py"]
