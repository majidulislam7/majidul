import io
import math
import shutil
import struct
import wave
from pathlib import Path

import pytest


@pytest.fixture
def media_tools():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe required for media integration tests")


@pytest.fixture
def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * n / 48000)))
                for n in range(19200)
            )
        )
    return stream.getvalue()


@pytest.fixture
def quiz_path():
    return Path(__file__).resolve().parents[1] / "quiz_10.csv"
