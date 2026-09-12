# NihongoHub bulk quiz video pipeline

Turn the existing 20-page Canva storyboard into a narrated Japanese vocabulary quiz. The first dataset is exactly **Cat, Dog, Apple, Fish, Book, Water, Flower, Mountain, Umbrella, Car**, with the supplied choices and correct answers. The Canva design is preserved.

The starter script's direct Fliki endpoint/request pattern is retained behind a provider interface. Its per-video unscheduled narration and unconditional background-audio assumptions are replaced with validated caching, one full-storyboard timeline, and automatic stream-aware composition. Its old, different CSV content is replaced with the authoritative storyboard dataset. Legacy `FLIKI_VOICE_ID` remains an English voice fallback for migration.

## Setup

Requires **Python 3.11+**, FFmpeg, and FFprobe. No MoviePy or large speech-model downloads.

macOS / Linux:

```bash
cd nihongohub-fliki-bulk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell:

```powershell
cd nihongohub-fliki-bulk
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell activation is restricted, use `.\.venv\Scripts\python.exe` directly.

Install FFmpeg using your normal package manager: `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Debian/Ubuntu), or `winget install Gyan.FFmpeg` (Windows). Reopen the terminal and check `ffmpeg -version` and `ffprobe -version`. Optional `FFMPEG_PATH` and `FFPROBE_PATH` point to executable files, not directories. A missing binary produces install guidance.

In `.env`, supply `FLIKI_API_KEY` and `FLIKI_VOICE_ID_EN`. A native Japanese `FLIKI_VOICE_ID_JA` is recommended; when absent it falls back to the English voice. Fliki requires **Enterprise API privilege**. A Canva subscription does not supply a Fliki key. The exact API contract and official references are in [API_RESEARCH.md](API_RESEARCH.md).

`FLIKI_VOICE_STYLE_ID` is optional. Styles are voice-specific: use optional `FLIKI_VOICE_STYLE_ID_JA` for a different Japanese voice instead of sending an English style to that voice. `.env` values never override pre-existing environment variables. No credentials are committed.

Find voices without synthesizing speech:

```bash
python generate.py --list-languages
python generate.py --list-dialects --language-id LANGUAGE_ID
python generate.py --list-voices --language-id LANGUAGE_ID --dialect-id DIALECT_ID
```

Select IDs from Fliki's results or its app. Audition English and native Japanese samples in Fliki; no voice IDs are invented.

## Normal run

Export the original Canva design as **one 90-second MP4** to `input/nihongohub_10_questions.mp4`. See [CANVA_SETUP.md](CANVA_SETUP.md) for the exact manual step and optional token-based automatic export.

```bash
python generate.py --data quiz_10.csv --video input/nihongohub_10_questions.mp4
```

Outputs:

- `output/NihongoHub_10_Questions_With_Voice.mp4`
- `manifests/NihongoHub_10_Questions_With_Voice.json`

If the source MP4 is absent, normal mode can still generate/cache narration, then exits with a missing-source report. Rerun the same command after placing the MP4. No dummy narration or substitute final video is produced.

## Modes

```bash
python generate.py --dry-run
python generate.py --tts-only
python generate.py --merge-only
python generate.py --force-tts --tts-only
python generate.py --export-canva
python generate.py --data NihongoHub_Fliki_Bulk_10.xlsx --dry-run
```

`--dry-run` validates data, prints placement timestamps, counts cached/uncached unique requests and characters, and writes a separate `.dry-run.json` plan. It performs no network calls and creates no final video. Japanese starts are explicitly dynamic until English durations have been measured. Cache status with missing voice IDs is provisional.

`--tts-only` generates, validates, and schedules all narration without requiring a video. `--merge-only` uses validated cache entries and **never calls Fliki**, including during duration fitting. Keep voice IDs, styles, format and timing configuration the same as the TTS run. The Fliki API key is not needed for cached merging.

`--force-tts` intentionally regenerates each unique request once per run. `--keep-temp` retains the composition filter graph. `--verbose` increases local diagnostics without enabling HTTP URL/header logging. `--export-canva` exports the unchanged source only when the input file is missing and a Canva Connect token is available.

## Narration and timing

Questions start 0.25s into each 6s question page. Answers start 0.20s into each 3s answer page. Default split narration uses English “The answer is B.” followed by Japanese “ねこ”. The Japanese start is calculated from the measured English duration plus a 0.12s gap, with a 0.15s end margin. There is no overlapping speech.

`--answer-mode combined` uses the workbook's complete “The answer is B. Neko. ねこ.” text through the English voice; use only after confirming that the chosen voice handles both languages. Split mode avoids relying on English romanization for Japanese pronunciation.

The last 3s of question pages are reserved for the learner/countdown. This makes the default question narration budget 2.60s and the answer group budget 2.65s. The script preserves existing countdown visuals; it does not animate them. See the countdown caveat in [CANVA_SETUP.md](CANVA_SETUP.md).

If a group is too long, its clips get one fitting attempt at up to 1.15× using Fliki's documented playback control. These variants are cached too. If still too long, the job fails visibly. Japanese is never locally stretched. Defaults are in `.env.example`; invalid or non-finite settings are rejected.

FFprobe inspects source duration, resolution, frame rate, codecs and audio streams. A duration discrepancy greater than 0.25s blocks merging and adds an inference report. Total duration alone cannot establish individual page boundaries. No blind scaling or trimming of speech is performed.

## Cache, cost and restart behavior

Every successful clip is fully decoded before publication at `cache/audio/<sha256>.<format>`. SHA-256 includes provider, voice, style, exact text, rate, format, sample rate and language. Repeated requests reuse validated files. Corrupt entries are rejected. Cache writes and final output replacement are atomic. A per-key lock prevents concurrent paid generation of the same key; if another worker owns it the job fails clearly. Only remove an abandoned `.lock` after confirming its process is no longer running.

Default split mode has **30 placements, 23 unique initial requests, 330 characters**: ten English questions, three reusable English answer-letter clips, and ten Japanese words. An uncached plan and any additional fitting requests are logged before payment. There is no interactive confirmation. Up to three HTTP attempts use exponential backoff for 429, selected 5xx statuses and connection/timeouts. Permanent 4xx responses stop immediately. Fliki does not document idempotency; an ambiguous POST timeout can lead to duplicate billing on retry. Do not interpret the initial call estimate as a guaranteed bill.

Manifests contain source inspection, dataset hash, page timing, planned and completed clips, measured durations, voice IDs, cache paths/hashes, FFmpeg version and explicit status. Signed URLs and tokens are excluded. Completed quiz groups are checkpointed; individual audio files are cached immediately. A rerun rebuilds scheduling from the current dataset and reuses valid cached clips, including fitting variants.

## Media composition

The filter graph is generated from the timeline, using 48kHz sample delays and `amix` with normalization disabled. Source audio, when present, is reduced to 20% volume. Without source audio the voice mix is the audio track. Optional local `assets/answer_chime.wav` is mixed quietly at answer-page starts; absent chime logs a message and continues. The final audio is AAC, 48kHz, 192kbps with a peak limiter. Video uses `-c:v copy`, preserving codec, dimensions and frame rate. Both streams and duration are verified before publishing the final path.

## Files and architecture

| File or directory | Responsibility |
| --- | --- |
| `quiz_10.csv`, `NihongoHub_Fliki_Bulk_10.xlsx` | Exact quiz content; one question per row |
| `models.py`, `timeline.py` | Input validation and deterministic page/clip specifications |
| `config.py`, `.env.example` | Configuration and secret-free setup example |
| `generate.py` | CLI, cost plan, fitting, checkpointing and orchestration |
| `services/tts/base.py`, `services/tts/fliki.py` | Provider interface and Fliki implementation |
| `services/http.py` | Sanitized bounded HTTP/retry/download operations |
| `services/audio.py`, `services/ffmpeg.py`, `services/video.py` | Media inspection, audio decoding and composition |
| `services/canva.py` | Optional unchanged-design MP4 export/poll/download |
| `input/`, `cache/audio/`, `output/`, `manifests/` | Ignored runtime media and job results |
| `scripts/update_workbook.py`, `tests/` | CSV-to-XLSX regeneration and offline tests |

## Validation and troubleshooting

```bash
python scripts/update_workbook.py
python -m pytest -q
python generate.py --dry-run
```

The workbook generator validates the CSV, writes bold headers, frozen first row/leading columns, wrapped cells and usable widths, and verifies equivalent workbook data. Tests mock paid HTTP requests and use synthetic tones/videos for real media checks. Media tests skip when FFmpeg is absent. Synthetic fixtures are not NihongoHub deliverables.

- **401/403 from Fliki:** verify API key, Enterprise API access and voice/style permissions.
- **Narration too long:** audition a shorter/faster natural voice or remove optional style; the script will not silently crop it. Avoid combined answers if they cannot fit.
- **Source duration mismatch:** correct the question/answer page durations in a Canva copy, re-export, and rerun.
- **Cache missing in merge-only:** run `--tts-only` with the same voices/format first.
- **Failed download/corrupt audio:** job fails and does not cache broken speech. Existing valid cache remains reusable.
- **Network unavailable:** retry in an environment that can reach Fliki's API/CDN and, for automatic export, Canva's API/export hosts.

## Future batches

The CLI accepts other CSV/XLSX filenames with sequential IDs, page numbers and 6s/3s timing. Provide a matching MP4 and unique `--output` and `--manifest` paths for each batch; run batches sequentially to respect account quotas and safely share the cache. The named first-ten datasets are constrained to ten rows. This release does not claim Google Sheets ingestion, automatic visual autofill, scheduler/queue operation, automatic OAuth login, pronunciation certification, or high-concurrency service deployment.
