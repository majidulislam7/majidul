"""Small HTTP fake shared by end-to-end tests; no external requests."""

from unittest.mock import Mock


def http_response(data=None, content=b""):
    result = Mock(status_code=200, headers={})
    result.json.return_value = data
    result.iter_content.return_value = [content]
    return result
