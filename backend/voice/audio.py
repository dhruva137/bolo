"""Audio helpers built on ffmpeg (system binary or bundled Python wheel).

clean():        noisy shop voice note -> denoised 16 kHz mono WAV for speech-to-text
to_voice_note(): TTS mp3/wav -> OGG/Opus mono, which WhatsApp shows as a native voice note
"""
import io
import os
import shutil
import subprocess
import tempfile
import wave

# High-pass removes fan/traffic rumble, low-pass removes hiss, afftdn is an FFT denoiser,
# dynaudnorm evens out loudness so quiet speakers aren't lost.
DENOISE = "highpass=f=100,lowpass=f=7000,afftdn=nr=12:nf=-30:tn=1,dynaudnorm=f=150:g=15"


def _ffmpeg(data: bytes, in_ext: str, out_ext: str, args: list[str]) -> bytes:
    binary = shutil.which("ffmpeg")
    if not binary:
        from imageio_ffmpeg import get_ffmpeg_exe
        binary = get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as d:
        # FFmpeg detects the input container from its header.
        src, dst = os.path.join(d, "input"), os.path.join(d, f"out.{out_ext}")
        with open(src, "wb") as f:
            f.write(data)
        subprocess.run([binary, "-nostdin", "-y", "-loglevel", "error", "-threads", "1", "-filter_threads", "1",
                        "-i", src, *args, "-threads", "1", dst],
                       check=True, timeout=90, capture_output=True)
        with open(dst, "rb") as f:
            return f.read()


def clean(audio: bytes, in_ext: str = "ogg") -> bytes:
    return _ffmpeg(audio, in_ext, "wav", ["-af", DENOISE, "-ar", "16000", "-ac", "1"])


def wav_chunks(wav: bytes, seconds: int = 30):
    """Yield complete PCM WAV files. Every input frame occurs once, in order."""
    with wave.open(io.BytesIO(wav), "rb") as source:
        frames_per_part = source.getframerate() * seconds
        if source.getnframes() <= frames_per_part:
            yield wav
            return
        while frames := source.readframes(frames_per_part):
            part = io.BytesIO()
            with wave.open(part, "wb") as dest:
                dest.setparams(source.getparams())
                dest.writeframes(frames)
            yield part.getvalue()


def to_voice_note(audio: bytes, in_ext: str = "mp3") -> bytes:
    return _ffmpeg(audio, in_ext, "ogg",
                   ["-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", "-application", "voip"])
