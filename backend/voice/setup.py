"""Download the public multilingual Whisper tiny model once. Run from backend/."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
from urllib.request import urlopen

import config

REVISION = "d90ca5fe260221311c53c58e660288d3deb8d356"
BASE = f"https://huggingface.co/Systran/faster-whisper-tiny/resolve/{REVISION}"
FILES = ("config.json", "tokenizer.json", "vocabulary.txt", "model.bin")
MODEL_SHA256 = "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"


def download() -> None:
    folder = Path(config.LOCAL_STT_MODEL)
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = folder / name
        if target.is_file() and target.stat().st_size:
            if name != "model.bin":
                continue
            with target.open("rb") as file:
                if hashlib.file_digest(file, "sha256").hexdigest() == MODEL_SHA256:
                    continue
        print(f"Downloading {name}...", flush=True)
        # Publish each complete file atomically, including on an interrupted rerun.
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            staged = Path(tmp) / name
            for attempt in range(2):
                try:
                    with urlopen(f"{BASE}/{name}", timeout=45) as response, staged.open("wb") as out:
                        shutil.copyfileobj(response, out, length=1024 * 1024)
                    break
                except OSError:
                    if attempt:
                        raise
                    time.sleep(1)
            if name == "model.bin":
                with staged.open("rb") as file:
                    if hashlib.file_digest(file, "sha256").hexdigest() != MODEL_SHA256:
                        raise ValueError("Incomplete model download. Run setup again.")
            os.replace(staged, target)
    print(f"Offline speech model ready at {folder}")


if __name__ == "__main__":
    download()
