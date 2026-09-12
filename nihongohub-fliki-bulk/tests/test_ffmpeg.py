import array
import math
import subprocess

import pytest

from services.audio import validate_audio
from services.ffmpeg import binary, run
from services.tts.base import PipelineError
from services.video import compose, duration_report, inspect_video


def make_video(path, background=False, seconds=2):
    cmd = [
        binary("ffmpeg"),
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=orange:s=160x284:r=24:d={seconds}",
    ]
    if background:
        cmd += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=48000:duration={seconds}",
            "-c:a",
            "aac",
        ]
    run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])


def rms(path, start):
    data = subprocess.check_output(
        [
            binary("ffmpeg"),
            "-v",
            "error",
            "-ss",
            str(start),
            "-i",
            str(path),
            "-t",
            "0.15",
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-f",
            "f32le",
            "-",
        ]
    )
    samples = array.array("f", data)
    return math.sqrt(sum(v * v for v in samples) / len(samples))


@pytest.mark.parametrize("background", [False, True])
def test_actual_composition_preserves_video_and_times_voice(
    tmp_path, wav_bytes, media_tools, background
):
    source, voice, final = (
        tmp_path / "source.mp4",
        tmp_path / "voice.wav",
        tmp_path / "final.mp4",
    )
    make_video(source, background)
    voice.write_bytes(wav_bytes)
    clip = {"local_path": str(voice), "duration": validate_audio(voice), "start": 1.0}
    result = compose(source, [clip], final)
    assert final.is_file()
    assert result["duration"] == pytest.approx(2, abs=0.05)
    assert result["audio_streams"][0]["codec"] == "aac"
    assert result["audio_streams"][0]["sample_rate"] == "48000"
    assert (result["width"], result["height"], result["frame_rate"]) == (
        160,
        284,
        "24/1",
    )
    assert rms(final, 1.1) > rms(final, 0.3) * 3 + 0.01
    if background:
        assert rms(final, 0.3) == pytest.approx(rms(source, 0.3) * 0.2, rel=0.15)
    else:
        assert rms(final, 0.3) < 0.001


def test_duration_mismatch_is_not_scaled():
    report = duration_report({"duration": 100}, 90, 0.25)
    assert not report["compatible"]
    assert report["difference"] == 10
    assert "hypotheses" in report["inference"]


def test_corrupt_audio_rejected(tmp_path, media_tools):
    path = tmp_path / "bad.mp3"
    path.write_bytes(b"not audio")
    with pytest.raises(PipelineError):
        validate_audio(path)


def test_missing_binary_guidance(monkeypatch):
    monkeypatch.setenv("FFMPEG_PATH", "/nonexistent/ffmpeg")
    with pytest.raises(PipelineError, match="Install FFmpeg"):
        binary("ffmpeg")


def test_chime_supported(tmp_path, wav_bytes, media_tools):
    source, voice = tmp_path / "source.mp4", tmp_path / "a.wav"
    make_video(source)
    voice.write_bytes(wav_bytes)
    output = tmp_path / "final.mp4"
    compose(
        source,
        [{"local_path": str(voice), "duration": 0.4, "start": 1.0}],
        output,
        chime=voice,
        answer_starts=[0.1],
    )
    assert inspect_video(output)["audio_streams"]
