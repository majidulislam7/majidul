from argparse import Namespace
from itertools import pairwise

import pytest

from config import Config
from generate import generate_clips, plan_generation
from models import load_quiz
from services.tts.base import PipelineError, TTSResult
from services.tts.fliki import FlikiTTSProvider
from timeline import build_pages


def test_continuous_90_seconds(quiz_path):
    pages = build_pages(load_quiz(quiz_path))
    assert pages[0].start == 0
    assert pages[-1].start + pages[-1].duration == 90
    assert [p.number for p in pages] == list(range(1, 21))
    assert [p.duration for p in pages] == [6, 3] * 10
    assert all(a.start + a.duration == b.start for a, b in pairwise(pages))


def test_split_plan_deduplicates_english_answers(quiz_path, tmp_path):
    config = Config(voice_en="en", voice_ja="ja", cache_dir=tmp_path)
    provider = FlikiTTSProvider("", tmp_path)
    summary, clips = plan_generation(load_quiz(quiz_path), config, provider, "split")
    assert summary["clip_placements"] == 30
    assert (
        summary["initial_api_calls"] == 23
    )  # 10 questions + 3 answer letters + 10 kana
    assert clips[0]["start"] == 0.25
    assert clips[1]["start"] == 6.2
    assert clips[2]["start"] is None


@pytest.mark.parametrize(
    "first,faster,should_fail", [(1.0, 1.0, False), (2.8, 2.4, False), (4, 3.8, True)]
)
def test_duration_fit_and_dynamic_japanese(
    quiz_path, tmp_path, first, faster, should_fail
):
    class Provider(FlikiTTSProvider):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.rates = []

        def synthesize(
            self, text, *, language, voice_id, voice_style, playback_rate, **kwargs
        ):
            self.rates.append(playback_rate)
            seconds = (
                (first if playback_rate == 1 else faster)
                if text.startswith("What")
                else 0.8
            )
            return TTSResult(
                "fliki",
                voice_id,
                text,
                language,
                tmp_path / "a.wav",
                seconds,
                "wav",
                self.cache_key(text, voice_id, playback_rate=playback_rate),
                playback_rate,
                False,
            )

    provider = Provider("", tmp_path)
    config = Config(voice_en="en", voice_ja="ja")
    manifest = {"clips": [], "countdown_windows": []}
    args = Namespace(answer_mode="split", force_tts=False, merge_only=False)
    if should_fail:
        with pytest.raises(PipelineError, match="still exceeds"):
            generate_clips(
                load_quiz(quiz_path)[:1], config, provider, args, manifest, lambda: None
            )
    else:
        generate_clips(
            load_quiz(quiz_path)[:1], config, provider, args, manifest, lambda: None
        )
        assert manifest["clips"][2]["start"] == pytest.approx(6.2 + 0.8 + 0.12)
        assert manifest["countdown_windows"][0]["start"] == 3
        assert max(provider.rates) <= 1.15


@pytest.mark.parametrize(
    "settings",
    [
        {"question_offset": float("nan")},
        {"answer_gap": -1},
        {"max_playback_rate": 1.16},
        {"countdown_seconds": 6},
        {"duration_tolerance": 90},
    ],
)
def test_bad_config_rejected(settings):
    with pytest.raises(ValueError):
        Config(**settings)
