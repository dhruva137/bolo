"""Local speech engines. Voice notes and replies stay on the machine."""
import ctypes
from functools import lru_cache
from importlib.util import find_spec
import io
import os
from pathlib import Path
import threading
import wave

import config


def stt_ready() -> bool:
    folder = Path(config.LOCAL_STT_MODEL)
    return find_spec("faster_whisper") is not None and all(
        (folder / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
    )


@lru_cache(maxsize=1)
def _model(path: str):
    from faster_whisper import WhisperModel
    return WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=1, num_workers=1, local_files_only=True)


_stt_lock = threading.Lock()


def transcribe(wav: bytes) -> tuple[str, str | None, float]:
    """Decode actual audio using the installed multilingual model; never contact a hosted API."""
    import numpy as np
    # The clean step has already decoded this note. Feed normalized PCM directly
    # to Whisper so a second container decoder never changes the sample timeline.
    with wave.open(io.BytesIO(wav)) as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Local STT requires 16 kHz mono, signed 16-bit audio")
        pcm = source.readframes(source.getnframes())
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    with _stt_lock:
        model = _model(config.LOCAL_STT_MODEL)
        segments, info = model.transcribe(samples, beam_size=1, vad_filter=False,
                                          condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    lang = f"{info.language}-IN" if info.language else None
    return text, lang, info.language_probability


def tts_ready() -> bool:
    return find_spec("espeakng_loader") is not None


# eSpeak NG's synchronous C API supplies mono, signed 16-bit PCM to this callback.
_callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
_tts_lock = threading.Lock()


@lru_cache(maxsize=1)
def _synthesizer():
    import espeakng_loader
    library = ctypes.CDLL(str(espeakng_loader.get_library_path()))
    library.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    library.espeak_SetSynthCallback.argtypes = [_callback_type]
    library.espeak_SetSynthCallback.restype = None
    library.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    library.espeak_Synth.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
                                     ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    data_parent = Path(espeakng_loader.get_data_path()).parent
    rate = library.espeak_Initialize(2, 0, os.fsencode(data_parent), 0x8000)
    if rate <= 0:
        raise RuntimeError("eSpeak NG could not open its bundled voices")
    return library, rate


def synthesize_wav(text: str, language: str) -> bytes:
    """Speak the supplied text with eSpeak NG, including Hindi and Kannada native scripts."""
    voice = language.split("-")[0].lower() or "en"
    pcm = bytearray()

    @_callback_type
    def collect(samples, count, _events):
        if samples and count > 0:
            pcm.extend(ctypes.string_at(samples, count * 2))
        return 0

    # eSpeak shares voice and callback state across all calls in a process.
    with _tts_lock:
        library, rate = _synthesizer()
        if library.espeak_SetVoiceByName(voice.encode("ascii")) != 0:
            raise ValueError(f"eSpeak NG has no voice for {language}")
        library.espeak_SetSynthCallback(collect)
        data = text.encode("utf-8")
        # POS_CHARACTER = 1, espeakCHARS_UTF8 = 1. Plain text, no SSML.
        status = library.espeak_Synth(data, len(data) + 1, 0, 1, 0, 1, None, None)
        if status or not pcm:
            raise ValueError("eSpeak NG could not synthesize the reply")
    out = io.BytesIO()
    with wave.open(out, "wb") as dest:
        dest.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        dest.writeframes(pcm)
    return out.getvalue()
