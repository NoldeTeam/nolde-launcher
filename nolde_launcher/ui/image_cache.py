"""Cover and logo artwork: fetched over HTTPS from allow-listed hosts, cached on disk,
and kept in memory with a least-recently-used limit so RAM stays bounded."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

IMAGE_HOSTS = {"images.launchbox-app.com", "gamesdb-images.launchbox.gg"}
MAX_IMAGE_BYTES = 3 * 1024 * 1024


def is_allowed_image_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "") in IMAGE_HOSTS


class ImageCache(QObject):
    ready = Signal(str)  # url whose pixmap is now available

    def __init__(self, cache_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._dir = Path(cache_dir) / "covers"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pixmaps: OrderedDict[str, QPixmap] = OrderedDict()
        self._limit = 60
        self._disk_limit = 500 * 1024 * 1024
        self._enabled = True
        self._failed: set[str] = set()
        self._pending: set[str] = set()
        self._lock = threading.Lock()

    # ----- settings -----

    def set_enabled(self, enabled: bool) -> None:
        """Off means no downloads and no drawing of artwork. Memory is released immediately."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self._pixmaps.clear()

    def set_limit(self, limit: int) -> None:
        self._limit = max(1, int(limit))
        self._trim()

    def set_disk_limit(self, megabytes: int) -> None:
        self._disk_limit = max(1, int(megabytes)) * 1024 * 1024
        self.prune_disk()

    def disk_usage(self) -> int:
        return sum(p.stat().st_size for p in self._dir.glob("*.img") if p.is_file())

    def prune_disk(self) -> int:
        """Remove the least recently written artwork until the folder fits its limit.
        Returns the number of bytes freed."""
        files = [p for p in self._dir.glob("*.img") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        freed = 0
        for path in sorted(files, key=lambda p: p.stat().st_mtime):
            if total <= self._disk_limit:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
            freed += size
        return freed

    def clear_disk(self) -> None:
        for path in self._dir.glob("*.img"):
            path.unlink(missing_ok=True)
        self._pixmaps.clear()

    @property
    def memory_count(self) -> int:
        return len(self._pixmaps)

    # ----- access -----

    def pixmap(self, url: str) -> QPixmap | None:
        if not url or not self._enabled or url in self._failed:
            return None
        if url in self._pixmaps:
            self._pixmaps.move_to_end(url)
            return self._pixmaps[url]
        path = self._path_for(url)
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._remember(url, pix)
                return pix
        self._fetch_async(url)
        return None

    def _remember(self, url: str, pix: QPixmap) -> None:
        self._pixmaps[url] = pix
        self._pixmaps.move_to_end(url)
        self._trim()

    def _trim(self) -> None:
        while len(self._pixmaps) > self._limit:
            self._pixmaps.popitem(last=False)  # least recently used

    def _path_for(self, url: str) -> Path:
        return self._dir / (hashlib.sha256(url.encode()).hexdigest() + ".img")

    def _fetch_async(self, url: str) -> None:
        if not is_allowed_image_url(url):
            self._failed.add(url)
            return
        with self._lock:
            if url in self._pending:
                return
            self._pending.add(url)
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, url: str) -> None:
        path = self._path_for(url)
        try:
            with requests.get(url, stream=True, timeout=(10, 20),
                              headers={"User-Agent": "NoldeLauncher/0.1"}) as resp:
                if resp.status_code != 200 or not resp.headers.get("Content-Type", "").startswith("image/"):
                    raise ValueError("unexpected response")
                if not is_allowed_image_url(resp.url):
                    raise ValueError("redirected to a disallowed host")
                data = bytearray()
                for chunk in resp.iter_content(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("image too large")
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(bytes(data))
            tmp.replace(path)
            self.prune_disk()
        except (requests.RequestException, ValueError, OSError):
            self._failed.add(url)
        finally:
            with self._lock:
                self._pending.discard(url)
            self.ready.emit(url)
