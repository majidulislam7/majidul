"""Timestamped speech mix with stream-copied video and atomic final publication."""

import logging
import shutil
import tempfile
from itertools import pairwise
from pathlib import Path

from services.audio import validate_audio
from services.ffmpeg import binary, duration, probe, run
from services.tts.base import PipelineError

LOG = logging.getLogger(__name__)


def inspect_video(path: Path) -> dict:
    info = probe(path)
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise PipelineError(f"No video stream: {path}")
    video = videos[0]
    audios = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    return {
        "path": str(path.resolve()),
        "duration": duration(info, "video"),
        "width": video["width"],
        "height": video["height"],
        "frame_rate": video.get("avg_frame_rate"),
        "video_codec": video.get("codec_name"),
        "audio_streams": [
            {
                "codec": s.get("codec_name"),
                "sample_rate": s.get("sample_rate"),
                "channels": s.get("channels"),
            }
            for s in audios
        ],
    }


def duration_report(source: dict, expected: float, tolerance: float) -> dict:
    actual = source["duration"]
    difference = actual - expected
    report = {
        "expected_duration": expected,
        "actual_duration": actual,
        "difference": difference,
        "tolerance": tolerance,
        "compatible": abs(difference) <= tolerance,
    }
    if not report["compatible"]:
        report["inference"] = (
            f"Total duration ratio is {actual / expected:.5f}; if every page were equal, "
            f"the average would be {actual / (expected / 4.5):.3f}s. "
            "MP4 does not reliably expose Canva page boundaries. These are hypotheses, "
            "not recovered timings. Verify the 6s/3s page durations in Canva and re-export."
        )
    return report


def compose(
    source: Path,
    clips: list[dict],
    output: Path,
    *,
    background_volume=0.20,
    chime: Path | None = None,
    answer_starts=(),
    keep_temp=False,
) -> dict:
    if source.resolve() == output.resolve():
        raise PipelineError("Source and final video paths must differ")
    source_info = inspect_video(source)
    total = source_info["duration"]
    if not clips:
        raise PipelineError("No narration clips to compose")
    for clip in clips:
        measured = validate_audio(Path(clip["local_path"]))
        if abs(measured - clip["duration"]) > 0.05:
            raise PipelineError("Narration duration changed since scheduling")
        if clip["start"] < 0 or clip["start"] + measured > total + 0.01:
            raise PipelineError("Narration extends outside the source video")
    ordered = sorted(clips, key=lambda c: c["start"])
    if any(
        a["start"] + a["duration"] > b["start"] + 0.001 for a, b in pairwise(ordered)
    ):
        raise PipelineError("Narration clips overlap")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="compose-", dir=output.parent))
    try:
        command = [
            binary("ffmpeg"),
            "-hide_banner",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
        ]
        filters, labels = [], []
        for index, clip in enumerate(clips, 1):
            command += ["-i", str(clip["local_path"])]
            samples = round(clip["start"] * 48000)
            filters.append(
                f"[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS,adelay={samples}S:all=1[s{index}]"
            )
            labels.append(f"[s{index}]")
        filters.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
            f"apad,atrim=duration={total},asetpts=PTS-STARTPTS[voice]"
        )
        mix_labels = ["[voice]"]
        if source_info["audio_streams"]:
            filters.append(
                f"[0:a:0]aresample=48000,aformat=channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS,volume={background_volume},apad,atrim=duration={total}[bg]"
            )
            mix_labels.append("[bg]")
        if chime and chime.is_file():
            chime_duration = validate_audio(chime)
            for number, start in enumerate(answer_starts):
                input_index = len(clips) + number + 1
                command += ["-i", str(chime)]
                limit = min(chime_duration, 0.6, total - start)
                filters.append(
                    f"[{input_index}:a:0]aresample=48000,aformat=channel_layouts=stereo,"
                    f"atrim=duration={limit},asetpts=PTS-STARTPTS,volume=0.15,"
                    f"adelay={round(start * 48000)}S:all=1[ch{number}]"
                )
                mix_labels.append(f"[ch{number}]")
        else:
            LOG.info("No answer chime asset found; continuing without chime.")
        filters.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:normalize=0:dropout_transition=0,"
            f"alimiter=limit=0.95:level=0:latency=1,apad,atrim=duration={total}[final_audio]"
        )
        graph = temp / "filter_graph.txt"
        graph.write_text(";\n".join(filters), encoding="utf-8")
        staged = temp / "final.mp4"
        command += [
            "-filter_complex_script",
            str(graph),
            "-map",
            "0:v:0",
            "-map",
            "[final_audio]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(staged),
        ]
        run(command, timeout=max(300, total * 8))
        final_info = inspect_video(staged)
        if not final_info["audio_streams"] or abs(final_info["duration"] - total) > 0.1:
            raise PipelineError("Final video failed stream/duration verification")
        for field in ("width", "height", "frame_rate", "video_codec"):
            if final_info[field] != source_info[field]:
                raise PipelineError(f"Final video changed source {field}")
        validate_audio(staged)
        staged.replace(output)
        final_info["path"] = str(output.resolve())
        return final_info
    finally:
        if keep_temp:
            LOG.info("Composition intermediates retained: %s", temp)
        else:
            shutil.rmtree(temp)
