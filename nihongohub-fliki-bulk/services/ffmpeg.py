import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from services.tts.base import PipelineError


def binary(name: str) -> str:
    candidate = os.getenv(f"{name.upper()}_PATH") or name
    found = shutil.which(candidate)
    if not found:
        raise PipelineError(
            f"{name} missing. Install FFmpeg (see README), add its bin directory to PATH, "
            f"or set {name.upper()}_PATH to the executable."
        )
    return found


def run(args: list[str], timeout: float = 300) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PipelineError(
            f"{Path(args[0]).name} could not run or exceeded {timeout}s timeout"
        ) from None
    if result.returncode:
        # Inputs are local files only. Avoid exposing command text, URLs, or environment.
        raise PipelineError(
            f"{Path(args[0]).name} failed (exit {result.returncode}): {result.stderr[-1500:]}"
        )
    return result


def probe(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise PipelineError(f"Media file missing or empty: {path}")
    try:
        return json.loads(
            run(
                [
                    binary("ffprobe"),
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ]
            ).stdout
        )
    except (ValueError, TypeError):
        raise PipelineError(f"Invalid ffprobe result: {path}") from None


def duration(info: dict, kind: str | None = None) -> float:
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == kind]
    raw = streams[0].get("duration") if streams else None
    try:
        value = float(raw or info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        value = 0
    if not math.isfinite(value) or value <= 0:
        raise PipelineError("Media has no finite positive duration")
    return value


def version() -> str:
    return run([binary("ffmpeg"), "-version"]).stdout.splitlines()[0]
