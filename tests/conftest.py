import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep every test off the real user profile.
import tempfile  # noqa: E402

_TEST_DATA = tempfile.mkdtemp(prefix="nolde-test-data-")
os.environ["NOLDE_DATA_DIR"] = _TEST_DATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


_exit_status = {"code": None}


def pytest_sessionfinish(session, exitstatus):
    _exit_status["code"] = exitstatus


def pytest_unconfigure(config):
    """Runs after pytest has printed its full report. On CI, end the process here, without
    touching any Qt object. Tests are finished at this point, and on Windows a Qt call made
    during interpreter shutdown crashed the process with exit code 1. Locally the normal
    shutdown is kept."""
    if not os.environ.get("CI") or _exit_status["code"] is None:
        return
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_status["code"])
