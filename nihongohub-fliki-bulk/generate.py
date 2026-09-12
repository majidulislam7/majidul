import csv
import os
import subprocess
from pathlib import Path

import requests

FLIKI_URL = "https://api.fliki.ai/v1/generate/text-to-speech"
BASE_DIR = Path(__file__).resolve().parent
DATA_CSV = BASE_DIR / "quiz_10.csv"
VIDEOS_DIR = BASE_DIR / "videos"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"


def generate_tts(text: str, out_path: Path) -> None:
    api_key = os.environ["FLIKI_API_KEY"]
    voice_id = os.environ["FLIKI_VOICE_ID"]
    payload = {
        "content": text,
        "voiceId": voice_id,
        "sampleRate": 24000,
        "playbackRate": 1.0,
        "format": "mp3",
    }
    style_id = os.getenv("FLIKI_VOICE_STYLE_ID")
    if style_id:
        payload["voiceStyleId"] = style_id

    r = requests.post(
        FLIKI_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    audio_url = data["audio"]

    audio = requests.get(audio_url, timeout=120)
    audio.raise_for_status()
    out_path.write_bytes(audio.content)


def merge_video_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", "[0:a]volume=0.18[bg];[1:a]volume=1.0[voice];[bg][voice]amix=inputs=2:duration=first[a]",
        "-map", "0:v:0",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    AUDIO_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    with DATA_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        quiz_id = row["id"].zfill(3)
        audio_path = AUDIO_DIR / f"{quiz_id}.mp3"
        video_path = VIDEOS_DIR / f"{quiz_id}.mp4"
        out_path = OUTPUT_DIR / f"{quiz_id}-final.mp4"

        print(f"[{quiz_id}] Generating Fliki voice...")
        generate_tts(row["voice_text"], audio_path)

        if not video_path.exists():
            print(f"[{quiz_id}] Missing video: {video_path}. Audio generated; skipping merge.")
            continue

        print(f"[{quiz_id}] Merging with FFmpeg...")
        merge_video_audio(video_path, audio_path, out_path)
        print(f"[{quiz_id}] Done: {out_path}")


if __name__ == "__main__":
    main()
