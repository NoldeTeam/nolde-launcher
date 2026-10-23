"""Run blocking work on a QThread and deliver results on the UI thread.

Callbacks are connected with an explicit QueuedConnection. Lambdas have no
thread affinity of their own, so without this they could run on the worker
thread and touch widgets from the wrong thread.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal

_ACTIVE: set["Worker"] = set()
_ACTIVE_LOCK = threading.Lock()
_QUEUED = Qt.ConnectionType.QueuedConnection


class Worker(QThread):
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[..., Any], args: tuple = (), parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self) -> None:
        try:
            result = self._fn(*self._args)
        except Exception as exc:  # delivered to the UI, never swallowed silently
            self.failed.emit(exc)
        else:
            self.succeeded.emit(result)
        finally:
            # Leave the registry BEFORE the thread ends. Once the thread has ended, Qt may delete
            # this object, and touching a deleted QThread crashes the process on Windows.
            with _ACTIVE_LOCK:
                _ACTIVE.discard(self)


def wait_for_workers(timeout_ms: int = 5000) -> None:
    """Wait for background threads before the process exits. Qt aborts if a QThread is
    destroyed while still running, so the application calls this when it closes.
    Only workers still in the registry are touched: those have not finished, so Qt has
    not deleted them yet."""
    with _ACTIVE_LOCK:
        pending = list(_ACTIVE)
    for worker in pending:
        worker.wait(timeout_ms)


def run_async(fn: Callable[..., Any], *args: Any, on_ok=None, on_err=None,
              parent: QObject | None = None) -> Worker:
    worker = Worker(fn, args, parent)
    _ACTIVE.add(worker)
    if on_ok is not None:
        worker.succeeded.connect(on_ok, _QUEUED)
    if on_err is not None:
        worker.failed.connect(on_err, _QUEUED)
    worker.finished.connect(worker.deleteLater, _QUEUED)
    worker.start()
    return worker
