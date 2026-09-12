from pathlib import Path

from services.ffmpeg import binary, duration, probe, run
from services.tts.base import PipelineError


def validate_audio(path: Path) -> float:
    info = probe(path)
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        raise PipelineError(f"No audio stream: {path}")
    seconds = duration(info, "audio")
    # ffprobe alone accepts some truncated files; fully decode and fail on errors.
    run(
        [
            binary("ffmpeg"),
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        timeout=180,
    )
    return seconds
