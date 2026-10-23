import threading

import pytest
import requests

from nolde_launcher.services.download_manager import (
    DownloadError, DownloadManager, DownloadStatus, download_to_file, sha256_of, validate_download_url,
)
from tests.helpers import FakeResponse, FakeSession

URL = "https://github.com/o/r/releases/download/v1/Game-Windows.zip"
BODY = b"x" * 5000


def test_full_download_streams_and_reports_progress(tmp_path):
    progress = []
    sess = FakeSession(lambda u, k: FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url=URL))
    out = download_to_file(URL, tmp_path / "game.zip", session=sess,
                           progress=lambda done, total: progress.append((done, total)))
    assert out.read_bytes() == BODY
    assert not (tmp_path / "game.zip.part").exists()
    assert progress[-1] == (len(BODY), len(BODY))


def test_sha256_mismatch_removes_file(tmp_path):
    sess = FakeSession(lambda u, k: FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url=URL))
    with pytest.raises(DownloadError) as info:
        download_to_file(URL, tmp_path / "g.zip", session=sess, expected_sha256="0" * 64)
    assert info.value.retryable is False
    assert not (tmp_path / "g.zip").exists() and not (tmp_path / "g.zip.part").exists()


def test_correct_sha256_is_accepted(tmp_path):
    import hashlib
    digest = hashlib.sha256(BODY).hexdigest()
    sess = FakeSession(lambda u, k: FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url=URL))
    out = download_to_file(URL, tmp_path / "g.zip", session=sess, expected_sha256=digest)
    assert sha256_of(out) == digest


def test_cancellation_deletes_partial_file(tmp_path):
    cancel = threading.Event()
    seen = {"n": 0}

    class Cancelling(FakeResponse):
        def iter_content(self, chunk_size=1024):
            for i in range(3):
                seen["n"] += 1
                if i == 1:
                    cancel.set()
                yield b"y" * 1024

    sess = FakeSession(lambda u, k: Cancelling(200, BODY, {"Content-Length": "3072"}, url=URL))
    from nolde_launcher.services.download_manager import DownloadCancelled
    with pytest.raises(DownloadCancelled):
        download_to_file(URL, tmp_path / "g.zip", session=sess, cancel_event=cancel)
    assert not (tmp_path / "g.zip.part").exists()


def test_interrupted_connection_keeps_partial_file_and_resumes(tmp_path):
    dest = tmp_path / "g.zip"
    first_half = BODY[:2048]
    failing = FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url=URL,
                           stream_error=requests.ConnectionError("reset"), chunk_size=2048)
    sess = FakeSession(lambda u, k: failing)
    with pytest.raises(DownloadError):
        download_to_file(URL, dest, session=sess)
    part = tmp_path / "g.zip.part"
    assert part.exists() and part.read_bytes() == first_half

    seen_headers = {}

    def resume(u, kwargs):
        seen_headers.update(kwargs["headers"])
        return FakeResponse(206, BODY[2048:], {"Content-Range": "bytes 2048-4999/5000",
                                                "Content-Length": str(len(BODY) - 2048)}, url=URL)

    out = download_to_file(URL, dest, session=FakeSession(resume))
    assert seen_headers["Range"] == "bytes=2048-"
    assert out.read_bytes() == BODY


def test_server_ignoring_range_restarts_cleanly(tmp_path):
    part = tmp_path / "g.zip.part"
    part.write_bytes(b"stale-bytes")
    sess = FakeSession(lambda u, k: FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url=URL))
    out = download_to_file(URL, tmp_path / "g.zip", session=sess)
    assert out.read_bytes() == BODY


def test_short_body_is_reported_as_incomplete(tmp_path):
    sess = FakeSession(lambda u, k: FakeResponse(200, BODY[:100], {"Content-Length": str(len(BODY))}, url=URL))
    with pytest.raises(DownloadError, match="before the file was complete"):
        download_to_file(URL, tmp_path / "g.zip", session=sess)
    assert (tmp_path / "g.zip.part").exists()  # kept for resume


@pytest.mark.parametrize("url", [
    "http://github.com/o/r/a.zip",
    "ftp://github.com/a.zip",
    "https://evil.example.com/a.zip",
    "https://github.com.evil.example/a.zip",
])
def test_disallowed_sources_are_refused(url):
    with pytest.raises(DownloadError):
        validate_download_url(url)


def test_redirect_to_unlisted_host_is_refused(tmp_path):
    hop = FakeResponse(302, url="https://github.com/o/r/a.zip")
    final = FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url="https://attacker.example/a.zip",
                         history=[hop])
    with pytest.raises(DownloadError, match="not an allowed download source"):
        download_to_file(URL, tmp_path / "g.zip", session=FakeSession(lambda u, k: final))


def test_http_404_is_not_retryable(tmp_path):
    sess = FakeSession(lambda u, k: FakeResponse(404, url=URL))
    with pytest.raises(DownloadError) as info:
        download_to_file(URL, tmp_path / "g.zip", session=sess)
    assert info.value.retryable is False


def test_manager_runs_download_and_deduplicates(qapp, tmp_path):
    gate = threading.Event()

    def responder(u, k):
        gate.wait(2)
        return FakeResponse(200, BODY, {"Content-Length": str(len(BODY))}, url=URL)

    manager = DownloadManager(session_factory=lambda: FakeSession(responder))
    first = manager.enqueue("proj", URL, tmp_path / "a.zip")
    second = manager.enqueue("proj", URL, tmp_path / "b.zip")
    assert first.task_id == second.task_id  # same URL while active: no duplicate transfer
    gate.set()
    _wait_for(lambda: first.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED))
    assert first.status is DownloadStatus.COMPLETED
    assert (tmp_path / "a.zip").read_bytes() == BODY


def test_manager_reports_failure_message(qapp, tmp_path):
    manager = DownloadManager(session_factory=lambda: FakeSession(
        lambda u, k: FakeResponse(500, url=URL)))
    task = manager.enqueue("proj", URL, tmp_path / "c.zip")
    _wait_for(lambda: not task.is_active)
    assert task.status is DownloadStatus.FAILED and "HTTP 500" in task.error


def _wait_for(predicate, timeout=5.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")
