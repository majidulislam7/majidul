"""Fliki's documented synchronous TTS endpoint, backed by validated content cache."""

import hashlib
import json
import logging
import math
import os
import shutil
import tempfile
from pathlib import Path

from services.audio import validate_audio
from services.http import HTTPClient, https_url
from services.tts.base import PipelineError, TTSProvider, TTSResult

LOG = logging.getLogger(__name__)
BASE_URL = "https://api.fliki.ai/v1"


class FlikiTTSProvider(TTSProvider):
    def __init__(self, api_key: str, cache_dir: Path, *, audio_format="mp3", http=None):
        self._api_key = api_key
        self.cache_dir = cache_dir
        self.audio_format = audio_format
        self.http = http or HTTPClient()

    def cache_key(
        self, text, voice_id, voice_style="", playback_rate=1.0, language="en"
    ):
        payload = {
            "provider": "fliki",
            "voice_id": voice_id,
            "voice_style": voice_style,
            "text": text,
            "playback_rate": float(playback_rate),
            "format": self.audio_format,
            "sample_rate": 48000,
            "language": language,
        }
        return hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def cached(self, text, voice_id, voice_style="", playback_rate=1.0, language="en"):
        key = self.cache_key(text, voice_id, voice_style, playback_rate, language)
        path = self.cache_dir / f"{key}.{self.audio_format}"
        if path.is_file():
            try:
                return TTSResult(
                    "fliki",
                    voice_id,
                    text,
                    language,
                    path,
                    validate_audio(path),
                    self.audio_format,
                    key,
                    playback_rate,
                    True,
                )
            except PipelineError:
                LOG.warning("Invalid audio cache entry: %s", key)
        return None

    def synthesize(
        self,
        text,
        output_path=None,
        *,
        language,
        voice_id=None,
        playback_rate=1.0,
        voice_style="",
        force=False,
        cache_only=False,
    ):
        if not voice_id:
            raise PipelineError(
                "Missing FLIKI_VOICE_ID_EN (and optionally FLIKI_VOICE_ID_JA)"
            )
        if not text.strip() or len(text) > 3000:
            raise PipelineError("Fliki content must contain 1–3000 characters")
        if (
            self.audio_format not in {"mp3", "wav", "ogg"}
            or not 0.5 <= playback_rate <= 3
        ):
            raise PipelineError("Unsupported Fliki audio format or playback rate")
        result = (
            None
            if force
            else self.cached(text, voice_id, voice_style, playback_rate, language)
        )
        if result is None:
            if cache_only:
                raise PipelineError(
                    "Required speech is not cached; run --tts-only before --merge-only"
                )
            if not self._api_key:
                raise PipelineError(
                    "Missing FLIKI_API_KEY; Enterprise API access is required"
                )
            key = self.cache_key(text, voice_id, voice_style, playback_rate, language)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self.cache_dir / f"{key}.{self.audio_format}"
            lock = self.cache_dir / f"{key}.lock"
            try:
                lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                raise PipelineError(
                    f"Cache entry is locked: {key}. Another job may be running; see README."
                ) from None
            temp_path = None
            try:
                os.close(lock_fd)
                # Another process could have completed between initial lookup and lock acquisition.
                result = (
                    None
                    if force
                    else self.cached(
                        text, voice_id, voice_style, playback_rate, language
                    )
                )
                if result is None:
                    payload = {
                        "content": text,
                        "voiceId": voice_id,
                        "sampleRate": 48000,
                        "playbackRate": playback_rate,
                        "format": self.audio_format,
                    }
                    if voice_style:
                        payload["voiceStyleId"] = voice_style
                    data = self.http.json(
                        "POST",
                        f"{BASE_URL}/generate/text-to-speech",
                        label="Fliki TTS",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if (
                        not isinstance(data, dict)
                        or not isinstance(data.get("audio"), str)
                        or isinstance(data.get("duration"), bool)
                        or not isinstance(data.get("duration"), (int, float))
                        or not math.isfinite(data["duration"])
                        or data["duration"] <= 0
                    ):
                        raise PipelineError(
                            "Fliki TTS: malformed response; expected audio URL and positive duration"
                        )
                    url = https_url(data["audio"])
                    fd, name = tempfile.mkstemp(
                        prefix=key + ".",
                        suffix="." + self.audio_format,
                        dir=self.cache_dir,
                    )
                    os.close(fd)
                    temp_path = Path(name)
                    self.http.download(url, temp_path)
                    measured = validate_audio(temp_path)
                    temp_path.replace(path)
                    result = TTSResult(
                        "fliki",
                        voice_id,
                        text,
                        language,
                        path,
                        measured,
                        self.audio_format,
                        key,
                        playback_rate,
                        False,
                    )
            finally:
                if temp_path:
                    temp_path.unlink(missing_ok=True)
                lock.unlink(missing_ok=True)
        if output_path and output_path.resolve() != result.local_path.resolve():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result.local_path, output_path)
        return result

    def catalog(self, resource: str, **params):
        if resource not in {"languages", "dialects", "voices"}:
            raise ValueError("Unknown catalog resource")
        if not self._api_key:
            raise PipelineError("Missing FLIKI_API_KEY")
        data = self.http.json(
            "GET",
            f"{BASE_URL}/{resource}",
            label=f"Fliki {resource}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            params=params,
        )
        if not isinstance(data, list):
            raise PipelineError(f"Fliki {resource}: expected JSON array")
        # Do not persist or print sample download URLs.
        return [
            {k: row[k] for k in ("_id", "name", "gender", "isUltra") if k in row}
            | {
                "styles": [
                    {k: style[k] for k in ("_id", "style") if k in style}
                    for style in row.get("styles", [])
                ]
            }
            for row in data
        ]
