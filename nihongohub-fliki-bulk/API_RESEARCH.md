# API and architecture verification

Checked during implementation in September 2026. No live Fliki request was made because credentials were absent.

## Fliki contract

| Item | Verified behavior |
| --- | --- |
| TTS request | `POST https://api.fliki.ai/v1/generate/text-to-speech` |
| Authentication | `Authorization: Bearer <API_KEY>`; JSON body |
| Required body | `content`, `voiceId` |
| Optional body used here | `voiceStyleId`, `sampleRate`, `playbackRate`, `format` |
| Other documented option | `pronunciations` array; not needed in this implementation |
| Response | JSON object containing `audio` URL and numeric `duration` |
| Formats | `mp3`, `wav`, `ogg`; default here is MP3 |
| Sample rates | 8000, 24000, 48000 Hz; this pipeline requests 48000 |
| Playback | API permits 0.5–3.0; pipeline deliberately caps automatic fitting at 1.15 |
| Text limit | 3000 characters per request |
| Request-frequency limits | No numeric Fliki requests/minute or concurrency quota found in the reviewed official docs; confirm the account-specific quota with Fliki. The client is sequential and handles 429. |
| Account access | Official introduction requires Enterprise privilege |

Sources: [TTS](https://developer.fliki.ai/docs/api/generate/tts), [access requirements](https://developer.fliki.ai/docs/intro).

Voice discovery uses `GET /v1/languages`, `GET /v1/dialects?languageId=...`, then `GET /v1/voices?languageId=...&dialectId=...`. Voice records expose `_id`, name, gender, and styles with their own `_id`. Language/dialect IDs are provider IDs, not assumed ISO codes. Japanese is selected through its voice ID; the TTS endpoint does not document a `language` body field, so no such field is sent. Language is retained in local metadata and cache keys.

Sources: [languages](https://developer.fliki.ai/docs/api/languages), [dialects](https://developer.fliki.ai/docs/api/dialects), [voices](https://developer.fliki.ai/docs/api/voices).

Fliki's documentation does not specify an idempotency key for this operation. Retrying a timed-out POST may incur a second charge if the first request completed remotely. The implementation limits attempts to three, caches successful downloads, and does not repeat the paid POST merely because a download failed. If all download retries fail, a later run may require synthesis again. Exact monetary cost cannot be inferred from character count without the account's pricing.

## MoneyPrinterTurbo reference review

Reviewed [voice.py](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/app/services/voice.py), [config.example.toml](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/config.example.toml), and [test_voice.py](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/test/services/test_voice.py). Useful patterns include explicit provider dispatch, environment/config separation, timeouts, configurable FFmpeg detection, opt-in live integration tests, and regression checks that corrupt speech is not silently replaced with silence.

This project independently implements a small provider interface, requests-based client, atomic audio cache, measured clip scheduling, and direct FFmpeg composition. It does not copy the monolithic provider dispatcher, MoviePy dependencies, web application, subtitles framework, or code from that project. No third-party source code was copied, so no copied-code attribution file is needed. MoneyPrinterTurbo remains a reference architecture.
