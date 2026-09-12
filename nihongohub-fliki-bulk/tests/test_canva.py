from unittest.mock import Mock

import pytest

from services.canva import export_storyboard
from services.tts.base import PipelineError


def test_export_poll_and_download(tmp_path, monkeypatch):
    http = Mock()
    http.json.side_effect = [
        {"job": {"id": "job1", "status": "in_progress"}},
        {
            "job": {
                "id": "job1",
                "status": "success",
                "urls": ["https://cdn.test/video"],
            }
        },
    ]
    http.download.side_effect = lambda url, path, **kw: path.write_bytes(b"mock mp4")
    monkeypatch.setattr("services.canva.inspect_video", lambda path: {"duration": 90})
    output = tmp_path / "source.mp4"
    export_storyboard("secret", "DAHU6cLMX7E", output, http=http, sleep=Mock())
    assert output.read_bytes() == b"mock mp4"
    assert http.json.call_args_list[0].kwargs["json"] == {
        "design_id": "DAHU6cLMX7E",
        "format": {"type": "mp4", "quality": "vertical_1080p"},
    }
    assert http.json.call_args_list[1].args[0] == "GET"


@pytest.mark.parametrize(
    "job", [{"status": "failed"}, {}, {"status": "success", "urls": []}]
)
def test_export_failure_is_visible(tmp_path, job):
    http = Mock()
    http.json.return_value = {"job": job}
    with pytest.raises(PipelineError):
        export_storyboard("secret", "design", tmp_path / "source.mp4", http=http)
