"""Readable text on coloured buttons, the text colour option, themed message boxes,
the empty library, and the installer shortcut icons."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QPushButton

from nolde_launcher.ui import palette
from nolde_launcher.ui.dialogs import ThemedMessage, _MessageDialog
from nolde_launcher.ui.theme import COLORS, build_stylesheet

INSTALLER = Path(__file__).resolve().parents[1] / "packaging" / "installer" / "NoldeLauncher.iss"


@pytest.fixture(autouse=True)
def restore_palette():
    yield
    palette.apply_palette()


# ----- readable text on coloured buttons -----

@pytest.mark.parametrize("accent,expected", [
    ("#ffffff", "#14171f"),  # white button: dark text
    ("#ffe066", "#14171f"),  # light yellow: dark text
    ("#2f6fed", "#ffffff"),  # the default blue: white text
    ("#101820", "#ffffff"),  # near black: white text
])
def test_text_on_an_accent_button_contrasts_with_it(accent, expected):
    palette.apply_palette("#0d1016", accent)
    assert COLORS["on_accent"] == expected


def test_primary_button_uses_the_computed_text_colour(qapp):
    palette.apply_palette("#0d1016", "#ffffff")
    assert f"color: {COLORS['on_accent']}" in build_stylesheet()


# ----- text colour option -----

def test_text_colour_can_be_chosen_and_is_used_for_text():
    palette.apply_palette("#0d1016", "#2f6fed", "#ffcc00")
    assert COLORS["text"] == "#ffcc00"
    assert COLORS["muted"] != "#ffcc00"  # the muted colour is a softer version of it


def test_text_colour_is_validated():
    with pytest.raises(ValueError):
        palette.apply_palette("#0d1016", "#2f6fed", "yellow")


def test_settings_keep_only_valid_text_colours(tmp_path):
    from nolde_launcher.storage.settings import SettingsService
    svc = SettingsService(tmp_path / "s.json")
    svc.update(theme_text="#ABCDEF")
    assert svc.settings.theme_text == "#ABCDEF"
    svc.update(theme_text="red")
    assert svc.settings.theme_text == "#ABCDEF"


# ----- themed message boxes -----

def test_question_returns_the_button_the_user_pressed(qapp, monkeypatch):
    def press_yes(self):
        self._choose(ThemedMessage.StandardButton.Yes)
        return 1
    monkeypatch.setattr(_MessageDialog, "exec", press_yes)
    assert ThemedMessage.question(None, "Title", "Text") == ThemedMessage.StandardButton.Yes


def test_question_defaults_to_no_when_closed(qapp, monkeypatch):
    monkeypatch.setattr(_MessageDialog, "exec", lambda self: 0)
    assert ThemedMessage.question(None, "Title", "Text") == ThemedMessage.StandardButton.No


def test_no_ui_module_imports_the_system_message_box():
    """Every message box is the launcher's own. The system QMessageBox must not be imported
    anywhere in the UI, otherwise its white title bar would come back."""
    import re
    root = Path(__file__).resolve().parents[1] / "nolde_launcher" / "ui"
    for path in root.glob("*.py"):
        if path.name == "dialogs.py":  # the one place that is allowed to talk to Qt's message box
            continue
        text = path.read_text(encoding="utf-8")
        imports = re.findall(r"from PySide6\.QtWidgets import \(?([^)\n]*(?:\n[^)\n]*)*?)\)?\s*\n", text)
        for block in imports:
            assert "QMessageBox" not in block, f"{path.name} imports the system message box"


# ----- empty library -----

def test_empty_library_shows_the_two_actions(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOLDE_DATA_DIR", str(tmp_path / "d"))
    from nolde_launcher.app import context
    from nolde_launcher.ui.library_page import LibraryPage
    services = context.build_services()
    page = LibraryPage(services, actions=_Actions(), project_lookup=lambda pid: None)
    page.show()
    page.refresh()
    qapp.processEvents()
    assert page.empty_panel.isVisible()
    asked, explored = [], []
    page.add_requested.connect(lambda: asked.append(True))
    page.explore_requested.connect(lambda: explored.append(True))
    buttons = {b.text(): b for b in page.empty_panel.findChildren(QPushButton)}
    from nolde_launcher.localization.i18n import t
    buttons[t("custom.add_button")].click()
    buttons[t("library.explore")].click()
    assert asked == [True] and explored == [True]


class _Actions:
    def play(self, pid): pass
    def open_project(self, pid): pass
    def check_updates(self): pass
    def library_changed(self): pass
    def verify_install(self, record): pass


# ----- installer shortcuts -----

def test_every_installer_shortcut_uses_the_launcher_icon():
    lines = [ln for ln in INSTALLER.read_text(encoding="utf-8").splitlines() if ln.startswith("Name: ") and "{group}" in ln or "autodesktop" in ln]
    assert len(lines) == 3
    for line in lines:
        assert "IconFilename" in line and "nolde.ico" in line
    assert "nolde.ico" in INSTALLER.read_text(encoding="utf-8").split("[Icons]")[0]  # copied with the program
