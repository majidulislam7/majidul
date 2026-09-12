# Implementation and execution report

## Implemented

Refactored the original three-file prototype only within `nihongohub-fliki-bulk/`. Added exact first-ten CSV/XLSX data, strict validation, a Fliki provider interface, separate English/Japanese voices, SHA-256 caching, audio decoding validation, bounded HTTP retries, duration fitting, deterministic page scheduling, source inspection, FFmpeg composition, manifests, CLI modes, and optional Canva Connect MP4 export. The Canva source was read and left unchanged.

## Verified in this environment

- Dependency installation completed in a local Python virtual environment.
- `python -m pytest -q`: **59 passed**, including actual FFmpeg integration tests.
- Full 90-second synthetic integration: 30 speech placements, 23 initial mocked syntheses, then a successful cache-only merge with no HTTP calls and no API key.
- FFmpeg output checks: video/audio streams, duration, source dimensions/frame rate, AAC at 48kHz, measured narration onset, source background reduced to approximately 20%, and optional chime mixing.
- Negative tests: bad quiz answers/timing, malformed API JSON, authentication errors without retries, 429/5xx/timeouts with bounded retries, download failure, corrupt speech, cache-only misses, invalid configuration, overlong speech, and source-duration mismatch before payment.
- `ruff check .` and `ruff format --check .`: passed.
- `python generate.py --dry-run`: succeeded; 20 pages, 90s; 30 placements, 23 unique initial requests, 330 characters, 0 cached speech clips. Voice-dependent cache estimates are provisional because voice IDs are missing.
- CSV/XLSX values were independently compared by tests. Workbook ranges were rendered and visually reviewed, including Japanese glyphs, headers and timing columns.
- `python generate.py --tts-only`: correctly returned exit code 1 before any paid request and saved the missing-credentials failure manifest.

## Genuine blockers for the real final video

1. `FLIKI_API_KEY` is absent. Fliki's official API requires Enterprise privilege.
2. `FLIKI_VOICE_ID_EN` is absent. `FLIKI_VOICE_ID_JA` is optional and recommended for pronunciation.
3. `input/nihongohub_10_questions.mp4` is absent. The connected Canva tool set could read the original design but did not expose MP4 export; no independent `CANVA_ACCESS_TOKEN` was configured. Follow `CANVA_SETUP.md` for the manual export, or provide a Canva Connect token for `--export-canva`.

No real Fliki narration or real NihongoHub final MP4 was generated. Synthetic fixtures are confined to temporary test directories and are not presented as the finished product. Japanese pronunciation, actual Canva page boundaries and countdown animation cannot be verified until real voices/source media are available.

## Local run artifacts

- `manifests/NihongoHub_10_Questions_With_Voice.dry-run.json`: validated plan.
- `manifests/NihongoHub_10_Questions_With_Voice.json`: explicit failed TTS attempt, including missing environment variable names.
- `NihongoHub_Fliki_Bulk_10.xlsx`: completed workbook.

Runtime manifests/media are intentionally ignored by Git; rerunning the CLI recreates the plan and status. The durable source, workbook, tests and this report are committed on the feature branch.

## Normal command

From `nihongohub-fliki-bulk/`, with the virtual environment active:

```bash
python generate.py --data quiz_10.csv --video input/nihongohub_10_questions.mp4
```
