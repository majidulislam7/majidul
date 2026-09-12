"""NihongoHub CSV → Fliki cache → timed narration → Canva MP4 composition."""

import argparse
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT, Config
from models import load_quiz
from services.canva import export_storyboard
from services.ffmpeg import binary, version
from services.tts.base import PipelineError
from services.tts.fliki import FlikiTTSProvider
from services.video import compose, duration_report, inspect_video
from timeline import build_pages, question_specs

LOG = logging.getLogger("nihongohub")
NAME = "NihongoHub_10_Questions_With_Voice"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def plan_generation(quizzes, config, provider, answer_mode, force=False):
    details, unique = [], {}
    for q in quizzes:
        specs = question_specs(q, config, answer_mode)
        for position, spec in enumerate(specs):
            if not spec.text.strip() or len(spec.text) > 3000:
                raise PipelineError(
                    f"{spec.id}: narration must contain 1–3000 characters"
                )
            key = provider.cache_key(
                spec.text,
                spec.voice_id,
                spec.voice_style,
                config.playback_rate,
                spec.language,
            )
            if key not in unique:
                cached = provider.cached(
                    spec.text,
                    spec.voice_id,
                    spec.voice_style,
                    config.playback_rate,
                    spec.language,
                )
                unique[key] = {
                    "cached": bool(cached) and not force,
                    "characters": len(spec.text),
                }
            start = (
                q.question_start + config.question_offset
                if position == 0
                else q.answer_start + config.answer_offset
            )
            dynamic = position == 2
            entry = {
                **asdict(spec),
                "hash": key,
                "cached": unique[key]["cached"],
                "start": None if dynamic else start,
                "timing": "after measured English answer + gap"
                if dynamic
                else "fixed page offset",
            }
            details.append(entry)
            LOG.info(
                "%-15s %-7s %s | %s",
                spec.id,
                spec.language,
                "dynamic" if dynamic else f"{start:06.2f}s",
                "cached" if entry["cached"] else "uncached",
            )
    missing = [entry for entry in unique.values() if not entry["cached"]]
    summary = {
        "clip_placements": len(details),
        "unique_requests": len(unique),
        "cached_requests": len(unique) - len(missing),
        "initial_api_calls": len(missing),
        "characters_to_synthesize": sum(entry["characters"] for entry in missing),
    }
    LOG.info(
        "TTS generation plan: %d placements; %d unique clips; %d cached; %d initial API calls; %d characters",
        len(details),
        len(unique),
        summary["cached_requests"],
        len(missing),
        summary["characters_to_synthesize"],
    )
    LOG.info(
        "Duration fitting may need one faster regeneration per unique clip; transient retries can also incur charges."
    )
    return summary, details


def generate_clips(quizzes, config, provider, args, manifest, checkpoint):
    memo = {}

    def get(spec, rate):
        key = provider.cache_key(
            spec.text, spec.voice_id, spec.voice_style, rate, spec.language
        )
        if key not in memo:
            memo[key] = provider.synthesize(
                spec.text,
                language=spec.language,
                voice_id=spec.voice_id,
                voice_style=spec.voice_style,
                playback_rate=rate,
                force=args.force_tts,
                cache_only=args.merge_only,
            )
        return memo[key]

    def fit(specs, budget, gap=0):
        results = [get(spec, config.playback_rate) for spec in specs]
        total = sum(result.duration for result in results) + gap * (len(results) - 1)
        if total <= budget:
            return results
        LOG.warning(
            "%s narration %.3fs exceeds %.3fs budget", specs[0].id, total, budget
        )
        # Fixed 1.15 cache key makes subsequent reruns reuse the fitted version.
        if config.max_playback_rate <= config.playback_rate:
            raise PipelineError(
                f"{specs[0].id}: narration too long at maximum configured rate"
            )
        rate = config.max_playback_rate
        LOG.warning(
            "One fitting attempt at %.2fx; no local Japanese time stretching", rate
        )
        pending = [
            s
            for s in specs
            if args.force_tts
            or not provider.cached(s.text, s.voice_id, s.voice_style, rate, s.language)
        ]
        LOG.info(
            "Fitting cost: up to %d new calls / %d characters",
            len(pending),
            sum(len(s.text) for s in pending),
        )
        results = [get(spec, rate) for spec in specs]
        total = sum(result.duration for result in results) + gap * (len(results) - 1)
        if total > budget:
            raise PipelineError(
                f"{specs[0].id}: narration {total:.3f}s still exceeds {budget:.3f}s at {rate}x"
            )
        return results

    for quiz in quizzes:
        specs = question_specs(quiz, config, args.answer_mode)
        question = fit(
            specs[:1],
            6
            - config.question_offset
            - config.safety_margin
            - config.countdown_seconds,
        )
        answers = fit(
            specs[1:],
            3 - config.answer_offset - config.safety_margin,
            config.answer_gap,
        )
        starts = [quiz.question_start + config.question_offset]
        cursor = quiz.answer_start + config.answer_offset
        for answer in answers:
            starts.append(cursor)
            cursor += answer.duration + config.answer_gap
        for spec, result, start in zip(specs, question + answers, starts):
            manifest["clips"].append(
                {
                    **asdict(result),
                    "id": spec.id,
                    "start": round(start, 6),
                    "voice_style": spec.voice_style,
                }
            )
        manifest["countdown_windows"].append(
            {
                "quiz_id": quiz.id,
                "start": quiz.answer_start - config.countdown_seconds,
                "end": quiz.answer_start,
                "note": "Reserved silent response time; existing Canva countdown visuals are preserved.",
            }
        )
        checkpoint()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT / "quiz_10.csv")
    p.add_argument(
        "--video", type=Path, default=ROOT / "input/nihongohub_10_questions.mp4"
    )
    p.add_argument("--output", type=Path, default=ROOT / f"output/{NAME}.mp4")
    p.add_argument("--manifest", type=Path, default=ROOT / f"manifests/{NAME}.json")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--tts-only", action="store_true")
    modes.add_argument("--merge-only", action="store_true")
    modes.add_argument("--list-languages", action="store_true")
    modes.add_argument("--list-dialects", action="store_true")
    modes.add_argument("--list-voices", action="store_true")
    p.add_argument("--language-id")
    p.add_argument("--dialect-id")
    p.add_argument("--answer-mode", choices=["split", "combined"], default="split")
    p.add_argument("--force-tts", action="store_true")
    p.add_argument(
        "--export-canva",
        action="store_true",
        help="Export unchanged design if input MP4 is missing",
    )
    p.add_argument("--keep-temp", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.force_tts and args.merge_only:
        p.error("--force-tts cannot be combined with --merge-only")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # HTTP debug logging can reveal signed URLs; do not enable it with --verbose.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    manifest = {
        "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_video": str(args.video.resolve()),
        "source_duration": None,
        "quiz_data_file": str(args.data.resolve()),
        "tts_provider": "fliki",
        "final_video_path": None,
        "requested_output": str(args.output.resolve()),
        "success": False,
        "status": "started",
        "clips": [],
        "countdown_windows": [],
    }
    manifest_path = (
        args.manifest.with_name(args.manifest.stem + ".dry-run.json")
        if args.dry_run
        else args.manifest
    )
    checkpoint = lambda: write_json(manifest_path, manifest)
    try:
        config = Config.from_env()
        provider = FlikiTTSProvider(
            config.api_key, config.cache_dir, audio_format=config.audio_format
        )
        if args.list_languages or args.list_dialects or args.list_voices:
            resource, params = "languages", {}
            if args.list_dialects or args.list_voices:
                if not args.language_id:
                    raise PipelineError("--language-id is required")
                resource, params = "dialects", {"languageId": args.language_id}
            if args.list_voices:
                if not args.dialect_id:
                    raise PipelineError("--dialect-id is required")
                resource = "voices"
                params["dialectId"] = args.dialect_id
            print(
                json.dumps(
                    provider.catalog(resource, **params), indent=2, ensure_ascii=False
                )
            )
            return 0
        quizzes = load_quiz(args.data)
        # The shipped storyboard is exactly 10 rows; alternate named datasets may contain more.
        if (
            args.data.name in {"quiz_10.csv", "NihongoHub_Fliki_Bulk_10.xlsx"}
            and len(quizzes) != 10
        ):
            raise PipelineError(
                "The first storyboard must contain exactly 10 questions"
            )
        pages = build_pages(quizzes)
        expected = pages[-1].start + pages[-1].duration
        manifest.update(
            {
                "pages": [asdict(page) for page in pages],
                "expected_duration": expected,
                "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
                "voice_ids": {"en": config.voice_en, "ja": config.voice_ja},
                "answer_mode": args.answer_mode,
                "timing_config": {
                    k: getattr(config, k)
                    for k in (
                        "question_offset",
                        "answer_offset",
                        "safety_margin",
                        "answer_gap",
                        "countdown_seconds",
                    )
                },
            }
        )
        manifest["tts_plan"], manifest["planned_clips"] = plan_generation(
            quizzes, config, provider, args.answer_mode, args.force_tts
        )
        LOG.info(
            "Timeline validated: %d pages, %.2fs; question pages 6s, answer pages 3s",
            len(pages),
            expected,
        )
        if not config.voice_en:
            LOG.warning(
                "Missing FLIKI_VOICE_ID_EN; cache estimates are provisional until voices are configured"
            )
        if config.voice_ja == config.voice_en:
            LOG.warning(
                "Japanese uses the English voice fallback; pronunciation must be auditioned before publishing"
            )
        try:
            binary("ffprobe")
            manifest["ffmpeg_version"] = version()
        except PipelineError as error:
            if not args.dry_run:
                raise
            manifest["ffmpeg_version"] = None
            LOG.warning("%s", error)
        if args.export_canva and not args.dry_run and not args.video.is_file():
            export_storyboard(config.canva_token, config.canva_design_id, args.video)
        source_mismatch = False
        if args.video.is_file():
            source = inspect_video(args.video)
            report = duration_report(source, expected, config.duration_tolerance)
            manifest.update(
                {
                    "source_inspection": source,
                    "source_duration": source["duration"],
                    "duration_report": report,
                }
            )
            source_mismatch = not report["compatible"]
            if source_mismatch:
                LOG.warning(
                    "Source duration differs: expected %.3fs, actual %.3fs, difference %+.3fs",
                    expected,
                    source["duration"],
                    report["difference"],
                )
        else:
            LOG.warning("Canva MP4 not available: %s", args.video.resolve())
        if args.dry_run:
            manifest.update(status="dry_run", success=not source_mismatch)
            checkpoint()
            return 1 if source_mismatch else 0
        if source_mismatch and not args.tts_only:
            raise PipelineError(
                "Source duration is incompatible. See manifest duration_report; correct Canva timing before merging."
            )
        if not config.voice_en:
            missing = ["FLIKI_VOICE_ID_EN"]
            if not config.api_key and not args.merge_only:
                missing.insert(0, "FLIKI_API_KEY")
            raise PipelineError(
                "Missing "
                + ", ".join(missing)
                + "; supply Fliki Enterprise credentials and a valid voice ID"
            )
        if (
            not config.api_key
            and not args.merge_only
            and manifest["tts_plan"]["initial_api_calls"]
        ):
            raise PipelineError(
                "Missing FLIKI_API_KEY; Enterprise API access is required"
            )
        generate_clips(quizzes, config, provider, args, manifest, checkpoint)
        if args.tts_only:
            manifest.update(status="tts_complete", success=True)
        elif not args.video.is_file():
            manifest.update(status="awaiting_source_video")
            raise PipelineError(
                f"TTS complete. Place/export Canva MP4 here: {args.video.resolve()}"
            )
        else:
            manifest["output_inspection"] = compose(
                args.video,
                manifest["clips"],
                args.output,
                background_volume=config.background_volume,
                chime=ROOT / "assets/answer_chime.wav",
                answer_starts=[q.answer_start for q in quizzes],
                keep_temp=args.keep_temp,
            )
            manifest.update(
                status="complete",
                success=True,
                final_video_path=str(args.output.resolve()),
            )
        checkpoint()
        return 0
    except (PipelineError, ValueError, OSError) as error:
        manifest.update(
            status="failed"
            if manifest["status"] != "awaiting_source_video"
            else manifest["status"],
            success=False,
            error=str(error),
        )
        checkpoint()
        LOG.error("%s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
