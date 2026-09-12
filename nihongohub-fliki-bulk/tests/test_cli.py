import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from config import Config
from generate import main
from services.ffmpeg import binary, run
from tests_helpers import http_response


def test_dry_run_no_network_or_final_video(tmp_path, monkeypatch, quiz_path):
    monkeypatch.setattr(
        "generate.Config.from_env", lambda: Config(cache_dir=tmp_path / "cache")
    )
    request = Mock(side_effect=AssertionError("Dry run attempted network"))
    monkeypatch.setattr("requests.Session.request", request)
    output, manifest = tmp_path / "final.mp4", tmp_path / "job.json"
    result = main(
        [
            "--dry-run",
            "--data",
            str(quiz_path),
            "--video",
            str(tmp_path / "missing.mp4"),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ]
    )
    assert result == 0
    request.assert_not_called()
    assert not output.exists() and not manifest.exists()
    data = json.loads((tmp_path / "job.dry-run.json").read_text())
    assert data["expected_duration"] == 90
    assert data["tts_plan"]["initial_api_calls"] == 23
    assert data["tts_plan"]["characters_to_synthesize"] == 330


def test_tts_then_cache_only_full_90s_merge(
    tmp_path, monkeypatch, quiz_path, wav_bytes, media_tools
):
    config = Config(
        api_key="TEST_ONLY_SECRET",
        voice_en="en-test",
        voice_ja="ja-test",
        audio_format="wav",
        cache_dir=tmp_path / "cache",
    )
    monkeypatch.setattr("generate.Config.from_env", lambda: config)

    def request(session, method, url, **kwargs):
        if method == "POST":
            return http_response(
                data={"audio": "https://cdn.test/speech?token=SECRET", "duration": 0.4}
            )
        return http_response(content=wav_bytes)

    network = Mock(side_effect=lambda *a, **kw: request(None, *a, **kw))
    monkeypatch.setattr("requests.Session.request", network)
    source, output, manifest = (
        tmp_path / "source.mp4",
        tmp_path / "final.mp4",
        tmp_path / "job.json",
    )
    arguments = [
        "--data",
        str(quiz_path),
        "--video",
        str(source),
        "--output",
        str(output),
        "--manifest",
        str(manifest),
    ]
    assert main(["--tts-only", *arguments]) == 0
    assert network.call_count == 46  # 23 syntheses and their downloads
    assert len(list(config.cache_dir.glob("*.wav"))) == 23
    assert not output.exists()
    data = json.loads(manifest.read_text())
    assert data["status"] == "tts_complete" and len(data["clips"]) == 30
    assert data["clips"][2]["start"] == pytest.approx(6.72)
    assert data["clips"][-1]["start"] == pytest.approx(87.72)
    run(
        [
            binary("ffmpeg"),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:s=64x112:r=12:d=90",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ]
    )
    config = replace(config, api_key="")
    network.reset_mock(side_effect=True)
    network.side_effect = AssertionError("Merge-only attempted network")
    assert main(["--merge-only", *arguments]) == 0
    network.assert_not_called()
    data = json.loads(manifest.read_text())
    assert data["status"] == "complete" and data["success"]
    assert data["output_inspection"]["duration"] == pytest.approx(90, abs=0.1)
    assert data["output_inspection"]["audio_streams"][0]["codec"] == "aac"
    assert "SECRET" not in manifest.read_text() and "token=" not in manifest.read_text()


def test_incompatible_source_stops_before_payment(
    tmp_path, monkeypatch, quiz_path, media_tools
):
    monkeypatch.setattr(
        "generate.Config.from_env",
        lambda: Config(voice_en="en", voice_ja="ja", cache_dir=tmp_path / "cache"),
    )
    source = tmp_path / "short.mp4"
    run(
        [
            binary("ffmpeg"),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=s=64x112:r=12:d=1",
            "-c:v",
            "libx264",
            str(source),
        ]
    )
    request = Mock(side_effect=AssertionError("Mismatched video triggered payment"))
    monkeypatch.setattr("requests.Session.request", request)
    manifest = tmp_path / "job.json"
    assert (
        main(
            [
                "--data",
                str(quiz_path),
                "--video",
                str(source),
                "--manifest",
                str(manifest),
            ]
        )
        == 1
    )
    request.assert_not_called()
    data = json.loads(manifest.read_text())
    assert data["duration_report"]["difference"] == -89
    assert not data["success"]
