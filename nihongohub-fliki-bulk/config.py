"""Environment configuration; paths are relative to this project, not the shell."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    api_key: str = field(default="", repr=False)
    voice_en: str = ""
    voice_ja: str = ""
    voice_style: str = ""
    voice_style_ja: str = ""
    question_offset: float = 0.25
    answer_offset: float = 0.20
    safety_margin: float = 0.15
    answer_gap: float = 0.12
    countdown_seconds: float = 3.0
    background_volume: float = 0.20
    playback_rate: float = 1.0
    max_playback_rate: float = 1.15
    duration_tolerance: float = 0.25
    audio_format: str = "mp3"
    cache_dir: Path = ROOT / "cache/audio"
    canva_token: str = field(default="", repr=False)
    canva_design_id: str = "DAHU6cLMX7E"

    def __post_init__(self):
        for name in (
            "question_offset",
            "answer_offset",
            "safety_margin",
            "answer_gap",
            "countdown_seconds",
            "background_volume",
            "duration_tolerance",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not 0.5 <= self.playback_rate <= self.max_playback_rate <= 1.15:
            raise ValueError(
                "Playback rates must satisfy 0.5 <= base <= maximum <= 1.15"
            )
        if self.background_volume > 1 or self.duration_tolerance > 0.5:
            raise ValueError(
                "Background volume must be <= 1; duration tolerance <= 0.5s"
            )
        if self.question_offset + self.safety_margin + self.countdown_seconds >= 6:
            raise ValueError("No question narration time remains")
        if self.answer_offset + self.safety_margin + self.answer_gap >= 3:
            raise ValueError("No answer narration time remains")
        if self.audio_format not in {"mp3", "wav", "ogg"}:
            raise ValueError("FLIKI_AUDIO_FORMAT must be mp3, wav, or ogg")

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        en = os.getenv("FLIKI_VOICE_ID_EN", "") or os.getenv("FLIKI_VOICE_ID", "")
        floats = {
            "question_offset": "QUESTION_VOICE_OFFSET",
            "answer_offset": "ANSWER_VOICE_OFFSET",
            "safety_margin": "VOICE_SAFETY_MARGIN",
            "answer_gap": "ANSWER_COMPONENT_GAP",
            "countdown_seconds": "COUNTDOWN_SECONDS",
            "background_volume": "BACKGROUND_VOLUME",
            "playback_rate": "FLIKI_PLAYBACK_RATE",
            "max_playback_rate": "MAX_PLAYBACK_RATE",
            "duration_tolerance": "VIDEO_DURATION_TOLERANCE",
        }
        overrides = {k: float(os.environ[v]) for k, v in floats.items() if os.getenv(v)}
        return cls(
            api_key=os.getenv("FLIKI_API_KEY", ""),
            voice_en=en,
            voice_ja=os.getenv("FLIKI_VOICE_ID_JA", "") or en,
            voice_style=os.getenv("FLIKI_VOICE_STYLE_ID", ""),
            voice_style_ja=os.getenv("FLIKI_VOICE_STYLE_ID_JA", ""),
            audio_format=os.getenv("FLIKI_AUDIO_FORMAT", "mp3"),
            cache_dir=Path(
                os.getenv("AUDIO_CACHE_DIR", str(ROOT / "cache/audio"))
            ).resolve(),
            canva_token=os.getenv("CANVA_ACCESS_TOKEN", ""),
            canva_design_id=os.getenv("CANVA_DESIGN_ID", "DAHU6cLMX7E"),
            **overrides,
        )
