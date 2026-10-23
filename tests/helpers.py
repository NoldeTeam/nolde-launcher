"""Test doubles. No test in this suite contacts the network."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


class FakeResponse:
    def __init__(self, status_code=200, body=b"", headers=None, url="https://github.com/x",
                 json_data=None, history=None, stream_error=None, chunk_size=1024):
        self.status_code = status_code
        self._body = body
        self.headers = dict(headers or {})
        self.url = url
        self._json = json_data
        self.history = history or []
        self._stream_error = stream_error
        self._chunk = chunk_size
        self.content = body

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def iter_content(self, chunk_size=1024):
        data = self._body
        for i in range(0, len(data), self._chunk):
            yield data[i:i + self._chunk]
            if self._stream_error and i + self._chunk < len(data):
                raise self._stream_error
        if self._stream_error and not data:
            raise self._stream_error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responder(url, kwargs)

    def close(self):
        pass


def make_zip(path: Path, entries: dict[str, bytes], symlinks: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 & 0xFFFF) << 16
            zf.writestr(info, target)
    return path


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()
