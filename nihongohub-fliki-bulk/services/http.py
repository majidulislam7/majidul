"""Bounded network operations with no URL/token leakage in errors."""

import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from services.tts.base import PipelineError

LOG = logging.getLogger(__name__)
TRANSIENT = {429, 500, 502, 503, 504}


def https_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise PipelineError("Service returned an invalid HTTPS download URL")
    return url


class HTTPClient:
    def __init__(self, session=None, attempts=3, sleep=time.sleep):
        self.session = session or requests.Session()
        self.attempts = attempts
        self.sleep = sleep

    def _delay(self, attempt, response=None):
        delay = 2**attempt
        if response is not None:
            try:
                delay = max(
                    delay, min(float(response.headers.get("Retry-After", 0)), 30)
                )
            except (TypeError, ValueError):
                pass
        self.sleep(delay)

    def request(self, method, url, *, label, **kwargs):
        https_url(url)
        for attempt in range(self.attempts):
            try:
                response = self.session.request(
                    method, url, timeout=(10, 120), allow_redirects=False, **kwargs
                )
            except (requests.ConnectionError, requests.Timeout):
                LOG.warning(
                    "%s connection/timeout (attempt %d/%d)",
                    label,
                    attempt + 1,
                    self.attempts,
                )
                if attempt + 1 == self.attempts:
                    raise PipelineError(
                        f"{label}: connection/timeout retries exhausted"
                    ) from None
                self._delay(attempt)
                continue
            except requests.RequestException:
                raise PipelineError(f"{label}: network request failed") from None
            status = response.status_code
            if 200 <= status < 300:
                return response
            LOG.warning(
                "%s HTTP %d (attempt %d/%d)", label, status, attempt + 1, self.attempts
            )
            if status not in TRANSIENT or attempt + 1 == self.attempts:
                response.close()
                hint = (
                    "; check credentials and API account access"
                    if status in {401, 403}
                    else ""
                )
                raise PipelineError(f"{label}: HTTP {status}{hint}")
            self._delay(attempt, response)
            response.close()
        raise PipelineError(f"{label}: retries exhausted")

    def json(self, method, url, *, label, **kwargs):
        response = self.request(method, url, label=label, **kwargs)
        try:
            return response.json()
        except (ValueError, TypeError):
            raise PipelineError(f"{label}: malformed JSON response") from None
        finally:
            response.close()

    def download(self, url: str, path: Path, *, max_bytes=100 * 1024 * 1024):
        # No bearer headers are ever sent to the audio/CDN download host.
        # Redirects are handled explicitly and remain HTTPS.
        for attempt in range(self.attempts):
            response = None
            try:
                current = https_url(url)
                for _ in range(6):
                    response = self.session.request(
                        "GET",
                        current,
                        timeout=(10, 120),
                        stream=True,
                        allow_redirects=False,
                    )
                    if response.status_code in {301, 302, 303, 307, 308}:
                        from urllib.parse import urljoin

                        current = https_url(
                            urljoin(current, response.headers.get("Location", ""))
                        )
                        response.close()
                        continue
                    break
                if response.status_code in TRANSIENT:
                    LOG.warning("Media download HTTP %d", response.status_code)
                    if attempt + 1 < self.attempts:
                        self._delay(attempt, response)
                        continue
                if not 200 <= response.status_code < 300:
                    raise PipelineError(f"Media download: HTTP {response.status_code}")
                total = 0
                with path.open("wb") as file:
                    for chunk in response.iter_content(64 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise PipelineError(
                                "Media download exceeded configured size limit"
                            )
                        file.write(chunk)
                if not total:
                    raise PipelineError("Media download is empty")
                return
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ):
                LOG.warning(
                    "Media download interrupted (attempt %d/%d)",
                    attempt + 1,
                    self.attempts,
                )
                if attempt + 1 == self.attempts:
                    raise PipelineError(
                        "Media download retries exhausted; generated audio was not cached"
                    ) from None
                self._delay(attempt)
            except requests.RequestException:
                raise PipelineError("Media download failed") from None
            finally:
                if response is not None:
                    response.close()
