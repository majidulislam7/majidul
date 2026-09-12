from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class PipelineError(RuntimeError):
    """Actionable error safe for logs and manifests; never contains server bodies."""


@dataclass(frozen=True)
class TTSResult:
    provider: str
    voice_id: str
    text: str
    language: str
    local_path: Path
    duration: float
    format: str
    hash: str
    playback_rate: float
    cached: bool


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: Path | None = None,
        *,
        language: str,
        voice_id: str | None = None,
        playback_rate: float = 1.0,
        voice_style: str = "",
        force: bool = False,
        cache_only: bool = False,
    ) -> TTSResult:
        """Generate or retrieve validated speech; never substitute silence."""
