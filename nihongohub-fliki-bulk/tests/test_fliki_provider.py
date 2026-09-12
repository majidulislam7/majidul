from unittest.mock import Mock

import pytest
import requests

from services.http import HTTPClient
from services.tts.base import PipelineError
from services.tts.fliki import FlikiTTSProvider


def response(status=200, data=None, content=b"", headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = data
    result.iter_content.return_value = [content]
    return result


def provider(tmp_path, responses):
    session = Mock()
    session.request.side_effect = responses
    client = HTTPClient(session=session, sleep=Mock())
    return FlikiTTSProvider(
        "TEST_SECRET_DO_NOT_LOG", tmp_path, audio_format="wav", http=client
    ), session


GOOD = {"audio": "https://cdn.example.test/audio.wav?signature=SECRET", "duration": 0.4}


def test_success_and_cache_only_one_paid_call(tmp_path, wav_bytes, media_tools):
    p, session = provider(tmp_path, [response(data=GOOD), response(content=wav_bytes)])
    first = p.synthesize(
        "ねこ", language="ja", voice_id="ja-voice", voice_style="style"
    )
    second = p.synthesize(
        "ねこ", language="ja", voice_id="ja-voice", voice_style="style"
    )
    assert first.duration == pytest.approx(0.4)
    assert not first.cached and second.cached
    assert first.hash == second.hash and len(first.hash) == 64
    assert session.request.call_count == 2  # one POST + one media GET
    post = session.request.call_args_list[0]
    assert post.args == ("POST", "https://api.fliki.ai/v1/generate/text-to-speech")
    assert post.kwargs["json"] == {
        "content": "ねこ",
        "voiceId": "ja-voice",
        "sampleRate": 48000,
        "playbackRate": 1.0,
        "format": "wav",
        "voiceStyleId": "style",
    }
    assert "headers" not in session.request.call_args_list[1].kwargs
    assert not list(tmp_path.glob("*.lock"))


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_permanent_failure_never_retries(tmp_path, status, caplog):
    p, session = provider(tmp_path, [response(status=status)])
    with pytest.raises(PipelineError, match=f"HTTP {status}"):
        p.synthesize("Hello", language="en", voice_id="en")
    assert session.request.call_count == 1
    assert "TEST_SECRET" not in caplog.text
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure", [429, 500, 502, 503, 504, "timeout", "connection"])
def test_transient_retry(tmp_path, wav_bytes, media_tools, failure):
    initial = (
        requests.Timeout("SECRET")
        if failure == "timeout"
        else requests.ConnectionError("SECRET")
        if failure == "connection"
        else response(status=failure, headers={"Retry-After": "2"})
    )
    p, session = provider(
        tmp_path, [initial, response(data=GOOD), response(content=wav_bytes)]
    )
    assert p.synthesize("Hello", language="en", voice_id="en").duration > 0
    assert session.request.call_count == 3
    p.http.sleep.assert_called_once()


def test_retry_exhaustion(tmp_path):
    p, session = provider(tmp_path, [response(status=429) for _ in range(3)])
    with pytest.raises(PipelineError, match="HTTP 429"):
        p.synthesize("Hello", language="en", voice_id="en")
    assert session.request.call_count == 3


@pytest.mark.parametrize(
    "data",
    [
        {},
        [],
        {"audio": "https://example.com/a", "duration": "3"},
        {"audio": "https://example.com/a", "duration": float("nan")},
        {"audio": "http://example.com/a", "duration": 1},
        {"audio": "https://example.com/a", "duration": True},
    ],
)
def test_malformed_response(tmp_path, data):
    p, session = provider(tmp_path, [response(data=data)])
    with pytest.raises(PipelineError):
        p.synthesize("Hello", language="en", voice_id="en")
    assert session.request.call_count == 1


def test_invalid_json(tmp_path):
    bad = response()
    bad.json.side_effect = ValueError("secret response body")
    p, _ = provider(tmp_path, [bad])
    with pytest.raises(PipelineError, match="malformed JSON") as exc:
        p.synthesize("Hello", language="en", voice_id="en")
    assert "secret response body" not in str(exc.value)


def test_download_failure_does_not_repeat_paid_post(tmp_path):
    p, session = provider(tmp_path, [response(data=GOOD), response(status=403)])
    with pytest.raises(PipelineError, match="download: HTTP 403"):
        p.synthesize("Hello", language="en", voice_id="en")
    assert session.request.call_count == 2
    assert not list(tmp_path.iterdir())


def test_corrupt_download_never_cached(tmp_path, media_tools):
    p, _ = provider(tmp_path, [response(data=GOOD), response(content=b"not audio")])
    with pytest.raises(PipelineError):
        p.synthesize("Hello", language="en", voice_id="en")
    assert not list(tmp_path.iterdir())


def test_force_regenerates(tmp_path, wav_bytes, media_tools):
    p, session = provider(
        tmp_path,
        [
            response(data=GOOD),
            response(content=wav_bytes),
            response(data=GOOD),
            response(content=wav_bytes),
        ],
    )
    p.synthesize("Hello", language="en", voice_id="en")
    assert not p.synthesize("Hello", language="en", voice_id="en", force=True).cached
    assert session.request.call_count == 4


def test_missing_cache_merge_only_never_calls_http(tmp_path):
    p, session = provider(tmp_path, [])
    with pytest.raises(PipelineError, match="not cached"):
        p.synthesize("Hello", language="en", voice_id="en", cache_only=True)
    session.request.assert_not_called()


def test_content_limit_checked_before_payment(tmp_path):
    p, session = provider(tmp_path, [])
    with pytest.raises(PipelineError, match="3000"):
        p.synthesize("x" * 3001, language="en", voice_id="en")
    session.request.assert_not_called()


def test_cache_keys_distinguish_all_request_settings(tmp_path):
    p, _ = provider(tmp_path, [])
    keys = {
        p.cache_key("hello", "voice"),
        p.cache_key("hello!", "voice"),
        p.cache_key("hello", "other"),
        p.cache_key("hello", "voice", "style"),
        p.cache_key("hello", "voice", playback_rate=1.15),
        p.cache_key("hello", "voice", language="ja"),
    }
    assert len(keys) == 6
    other = FlikiTTSProvider("", tmp_path, audio_format="mp3")
    assert other.cache_key("hello", "voice") not in keys
