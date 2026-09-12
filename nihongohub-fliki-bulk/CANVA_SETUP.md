# Canva source and export setup

The existing source is [NihongoHub — 10 Questions & Answers — Video Storyboard](https://www.canva.com/design/DAHU6cLMX7E/edit), design ID `DAHU6cLMX7E`. The connected Canva tools successfully returned its title, 20 pages, and all question/answer text. All ten questions match the supplied Cat → Car sequence. The original design was not edited or duplicated.

## Current access limitation

The Canva connector available during implementation supports reading this design but exposes no export operation. Its authentication is not a reusable Canva Connect OAuth token. No `CANVA_ACCESS_TOKEN` or source MP4 was available locally. Therefore no actual Canva MP4 export was produced in this session.

## One manual step

1. Open the existing design above in Canva.
2. Verify the 20-page order. Odd pages are questions at **6 seconds** each; even pages are answers at **3 seconds** each. Total: **90 seconds**. Preserve the design and its visual styling. If timing needs correction, duplicate the design first and fix the copy.
3. Use **Share → Download → MP4 Video**, select **all 20 pages**, and download as one video (1080p portrait when available).
4. Save it at `nihongohub-fliki-bulk/input/nihongohub_10_questions.mp4`.
5. Run `python generate.py`. The CLI detects the file at startup, probes it, and continues automatically. This is startup detection, not a background file watcher.

## Optional automated export

With a Canva Connect integration, obtain a valid user OAuth access token with `design:content:read` scope. Set `CANVA_ACCESS_TOKEN` in `.env`. Then run:

```bash
python generate.py --export-canva
```

This sends `POST https://api.canva.com/rest/v1/exports` with the existing design ID and `format: {type: "mp4", quality: "vertical_1080p"}`. It polls the returned job every 5 seconds, up to 10 minutes, using `GET /rest/v1/exports/{exportId}`. One completed MP4 is downloaded and validated atomically. Existing local input is reused. URLs and tokens are never written to the manifest. OAuth enrollment/token refresh remains the responsibility of the integration owner; the script does not extract connector credentials.

This normal editable design is **not assumed to support Brand Template autofill**. CSV/XLSX data does not change its visuals. Future question batches need a matching Canva MP4; this version automates the narration and composition.

## Countdown and timing limits

Canva text extraction shows a `5` on each question page; text extraction alone cannot establish whether that is an animated countdown or static text. The API inspection did not expose page timing or animation timing. Those remain unverified until the MP4 is available.

The pipeline reserves the final 3 seconds of each question page for the learner, ending question narration by 2.85s at default settings. It preserves existing Canva visuals and audio; it does not manufacture or animate a countdown. A full 5-second countdown following a roughly 2-second spoken question cannot fit inside a 6-second page. Check the actual countdown in the exported video and align its animation to the reserved response window on a **copy** if necessary. Do not extend the original timing blindly.

If total MP4 duration differs from 90s by more than 0.25s, composition stops with a report. An MP4's total duration cannot uniquely recover its 20 page boundaries. No global scaling is applied. Even a 90s total does not prove that every page boundary is correct; preview those boundaries before publication.

Official references: [Create export job](https://www.canva.dev/docs/connect/api-reference/exports/create-design-export-job/), [Get export job](https://www.canva.dev/docs/connect/api-reference/exports/get-design-export-job/).
