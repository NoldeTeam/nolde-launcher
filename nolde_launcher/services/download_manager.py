"""Background downloads with streaming, cancellation, resume and validation.

The transfer core (`download_to_file`) is plain Python and fully testable. The
`DownloadManager` QObject runs transfers on worker threads and reports progress
through Qt signals, so the UI thread is never blocked.

Pausing is intentionally not offered: this manager cannot pause an active
transfer. Interrupted transfers keep their partial file and can be resumed by
starting them again, when the server supports byte ranges.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QObject, Signal

ALLOWED_DOWNLOAD_HOSTS = {"github.com", "objects.githubusercontent.com",
                          "release-assets.githubusercontent.com",
                          "github-releases.githubusercontent.com"}
CHUNK_SIZE = 256 * 1024
PROGRESS_INTERVAL = 0.25
MAX_DOWNLOAD_BYTES = 4 * 1024 ** 3
MAX_CONCURRENT = 2


class DownloadError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class DownloadPaused(DownloadError):
    """Raised inside a transfer when the user pauses it. The partial file is kept."""

    def __init__(self) -> None:
        super().__init__("download was paused", retryable=True)


class DownloadCancelled(DownloadError):
    def __init__(self) -> None:
        super().__init__("download was cancelled", retryable=False)


class DownloadStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


def validate_download_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise DownloadError("refusing non-HTTPS URL", retryable=False)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise DownloadError(f"host {host!r} is not an allowed download source", retryable=False)
    return url


def download_to_file(
    url: str,
    dest: Path,
    *,
    session=None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    progress: Callable[[int, int | None], None] | None = None,
    expected_sha256: str | None = None,
    timeout: tuple[float, float] = (15, 60),
) -> Path:
    """Stream `url` into `dest`. Partial data lives in `dest.part` and is kept on
    network errors (for resume) but removed on cancellation or hash mismatch."""
    validate_download_url(url)
    session = session or requests.Session()
    cancel_event = cancel_event or threading.Event()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    existing = part.stat().st_size if part.exists() else 0
    headers = {"Accept-Encoding": "identity", "User-Agent": "NoldeLauncher/0.1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    try:
        with session.get(url, stream=True, timeout=timeout, headers=headers,
                         allow_redirects=True) as response:
            for hop in itertools.chain(response.history, [response]):
                validate_download_url(getattr(hop, "url", url))

            status = response.status_code
            if status == 416 and existing:
                # Partial file is larger than or equal to the remote file: restart.
                part.unlink(missing_ok=True)
                existing = 0
                raise DownloadError("partial file was invalid; restart the download")
            if status == 206 and existing:
                mode = "ab"
                total = _content_length(response)
                total = total + existing if total is not None else None
            elif status == 200:
                mode = "wb"
                existing = 0
                total = _content_length(response)
            else:
                raise DownloadError(f"server returned HTTP {status}",
                                    retryable=status >= 500)

            if total is not None and total > MAX_DOWNLOAD_BYTES:
                raise DownloadError("file is larger than the allowed limit", retryable=False)

            written = existing
            last_report = 0.0
            with open(part, mode) as fh:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if cancel_event.is_set():
                        raise DownloadCancelled()
                    if pause_event is not None and pause_event.is_set():
                        raise DownloadPaused()  # partial data stays in .part for resume
                    if not chunk:
                        continue
                    fh.write(chunk)
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise DownloadError("download exceeded the size limit", retryable=False)
                    now = time.monotonic()
                    if progress and now - last_report >= PROGRESS_INTERVAL:
                        progress(written, total)
                        last_report = now
                fh.flush()
                os.fsync(fh.fileno())
            if progress:
                progress(written, total)

        if total is not None and written != total:
            raise DownloadError("connection ended before the file was complete")
    except DownloadCancelled:
        part.unlink(missing_ok=True)
        raise
    except requests.RequestException as exc:
        # Keep the partial file so the next attempt can resume.
        raise DownloadError(f"network error: {exc.__class__.__name__}") from exc

    if expected_sha256 and sha256_of(part) != expected_sha256.lower():
        part.unlink(missing_ok=True)
        raise DownloadError("downloaded file failed its SHA-256 check", retryable=False)

    os.replace(part, dest)
    return dest


def _content_length(response) -> int | None:
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class DownloadTask:
    task_id: int
    project_id: str
    url: str
    destination: Path
    expected_sha256: str | None = None
    status: DownloadStatus = DownloadStatus.QUEUED
    bytes_done: int = 0
    total_bytes: int | None = None
    speed_bps: float | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    pause_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _speed_mark: tuple[float, int] | None = field(default=None, repr=False)

    @property
    def is_active(self) -> bool:
        """Still in progress or waiting to resume. A paused transfer counts as active."""
        return self.status in (DownloadStatus.QUEUED, DownloadStatus.RUNNING, DownloadStatus.PAUSED)


class DownloadManager(QObject):
    """Qt facade. Signals are emitted from worker threads and delivered to the
    UI thread through queued connections."""

    task_changed = Signal(object)  # DownloadTask

    def __init__(self, session_factory: Callable[[], object] | None = None,
                 max_concurrent: int = MAX_CONCURRENT, parent=None) -> None:
        super().__init__(parent)
        self._session_factory = session_factory or requests.Session
        self._tasks: dict[int, DownloadTask] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def set_max_concurrent(self, count: int) -> None:
        """Applies to transfers that start after this call. Running transfers finish normally."""
        with self._lock:
            self._slots = threading.BoundedSemaphore(max(1, min(int(count), 8)))

    def tasks(self) -> list[DownloadTask]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: t.task_id)

    def task(self, task_id: int) -> DownloadTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def enqueue(self, project_id: str, url: str, destination: Path,
                expected_sha256: str | None = None) -> DownloadTask:
        """Start a download. If the same URL is already active, that task is
        returned instead of starting a duplicate transfer."""
        validate_download_url(url)
        with self._lock:
            for existing in self._tasks.values():
                if existing.is_active and existing.url == url:
                    return existing
            task = DownloadTask(next(self._ids), project_id, url, Path(destination),
                                expected_sha256)
            self._tasks[task.task_id] = task
        threading.Thread(target=self._run, args=(task,), daemon=True,
                         name=f"download-{task.task_id}").start()
        self.task_changed.emit(task)
        return task

    def pause(self, task_id: int) -> None:
        """Stop after the current block. The partial file is kept so resume continues from it."""
        task = self.task(task_id)
        if task and task.status in (DownloadStatus.QUEUED, DownloadStatus.RUNNING):
            task.pause_event.set()

    def resume(self, task_id: int) -> bool:
        task = self.task(task_id)
        if task is None or task.status is not DownloadStatus.PAUSED:
            return False
        task.pause_event.clear()
        task.status = DownloadStatus.QUEUED
        self.task_changed.emit(task)
        threading.Thread(target=self._run, args=(task,), daemon=True,
                         name=f"download-{task.task_id}").start()
        return True

    def cancel(self, task_id: int) -> None:
        task = self.task(task_id)
        if task is None:
            return
        if task.status is DownloadStatus.PAUSED:
            # No connection is open, so nothing else will finish this task: clean up here.
            task.destination.with_name(task.destination.name + ".part").unlink(missing_ok=True)
            self._finish(task, DownloadStatus.CANCELLED, "")
        elif task.is_active:
            task.cancel_event.set()

    def remove(self, task_id: int) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and not task.is_active:
                del self._tasks[task_id]

    def clear_finished(self) -> None:
        with self._lock:
            for tid in [t.task_id for t in self._tasks.values() if not t.is_active]:
                del self._tasks[tid]

    def _run(self, task: DownloadTask) -> None:
        with self._slots:
            if task.cancel_event.is_set():
                self._finish(task, DownloadStatus.CANCELLED, "")
                return
            if task.pause_event.is_set():
                self._finish(task, DownloadStatus.PAUSED, "")
                return
            task.status = DownloadStatus.RUNNING
            self.task_changed.emit(task)

            def on_progress(done: int, total: int | None) -> None:
                task.bytes_done = done
                task.total_bytes = total
                now = time.monotonic()
                if task._speed_mark:
                    t0, b0 = task._speed_mark
                    if now > t0:
                        task.speed_bps = (done - b0) / (now - t0)
                task._speed_mark = (now, done)
                self.task_changed.emit(task)

            session = self._session_factory()
            try:
                download_to_file(task.url, task.destination, session=session,
                                 cancel_event=task.cancel_event, pause_event=task.pause_event,
                                 progress=on_progress, expected_sha256=task.expected_sha256)
                self._finish(task, DownloadStatus.COMPLETED, "")
            except DownloadPaused:
                self._finish(task, DownloadStatus.PAUSED, "")
            except DownloadCancelled:
                self._finish(task, DownloadStatus.CANCELLED, "")
            except DownloadError as exc:
                self._finish(task, DownloadStatus.FAILED, str(exc))
            except Exception as exc:  # last resort: never crash the worker silently
                self._finish(task, DownloadStatus.FAILED, f"unexpected error: {exc.__class__.__name__}")
            finally:
                session.close()

    def _finish(self, task: DownloadTask, status: DownloadStatus, error: str) -> None:
        task.status = status
        task.error = error
        task.speed_bps = None
        if status == DownloadStatus.COMPLETED and task.total_bytes is None:
            task.total_bytes = task.bytes_done
        self.task_changed.emit(task)
