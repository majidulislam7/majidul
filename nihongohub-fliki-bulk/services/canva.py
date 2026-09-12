"""Optional unchanged Canva Connect MP4 export. Never edits or autofills designs."""

import time
from pathlib import Path

from services.http import HTTPClient
from services.tts.base import PipelineError
from services.video import inspect_video


def export_storyboard(
    token: str,
    design_id: str,
    destination: Path,
    *,
    http=None,
    timeout=600,
    sleep=time.sleep,
    clock=time.monotonic,
):
    if not token:
        raise PipelineError(
            "Missing CANVA_ACCESS_TOKEN; export MP4 manually as described in CANVA_SETUP.md"
        )
    client = http or HTTPClient()
    base = "https://api.canva.com/rest/v1/exports"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = client.json(
        "POST",
        base,
        label="Canva export",
        headers=headers,
        json={
            "design_id": design_id,
            "format": {"type": "mp4", "quality": "vertical_1080p"},
        },
    )
    deadline = clock() + timeout
    while True:
        job = data.get("job", {}) if isinstance(data, dict) else {}
        if job.get("status") == "success":
            urls = job.get("urls")
            if (
                not isinstance(urls, list)
                or len(urls) != 1
                or not isinstance(urls[0], str)
            ):
                raise PipelineError(
                    "Canva export did not return one full-storyboard MP4"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_suffix(".download.mp4")
            try:
                client.download(urls[0], temp, max_bytes=2 * 1024**3)
                inspect_video(temp)
                temp.replace(destination)
            finally:
                temp.unlink(missing_ok=True)
            return
        if job.get("status") == "failed":
            raise PipelineError(
                "Canva export failed; check design export permissions or premium assets"
            )
        if job.get("status") != "in_progress" or not isinstance(job.get("id"), str):
            raise PipelineError("Canva export: malformed job response")
        if clock() >= deadline:
            raise PipelineError("Canva MP4 export timed out")
        sleep(5)
        data = client.json(
            "GET", f"{base}/{job['id']}", label="Canva export status", headers=headers
        )
