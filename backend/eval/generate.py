"""Regenerate the public synthetic fixtures with eSpeak NG. Run from backend/."""
import csv
import io
import math
from array import array
from pathlib import Path
import random
import wave

from voice.local import synthesize_wav

HERE = Path(__file__).resolve().parent


def with_noise(wav, db, seed):
    with wave.open(io.BytesIO(wav)) as source:
        params = source.getparams()
        samples = array("h", source.readframes(params.nframes))
    rng = random.Random(seed)
    signal_rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    noise_rms = signal_rms / 10 ** (db / 20)
    mixed = array("h", (max(-32768, min(32767, round(x + rng.gauss(0, noise_rms)))) for x in samples))
    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setparams(params)
        destination.writeframes(mixed.tobytes())
    return output.getvalue()


def main():
    folder = HERE / "audio"
    folder.mkdir(exist_ok=True)
    with (HERE / "cases.csv").open(encoding="utf8", newline="") as source:
        for case in csv.DictReader(source):
            wav = synthesize_wav(case["reference"], case["voice"])
            if case["snr_db"]:
                wav = with_noise(wav, float(case["snr_db"]), case["id"])
            (folder / (case["id"] + ".wav")).write_bytes(wav)
            print(case["id"], len(wav), flush=True)


if __name__ == "__main__":
    main()
