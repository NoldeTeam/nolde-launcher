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
