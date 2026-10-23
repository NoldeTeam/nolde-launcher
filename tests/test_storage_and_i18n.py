import json

from nolde_launcher.localization.i18n import available_locales, t
from nolde_launcher.storage.json_store import JsonStore
from nolde_launcher.storage.settings import SettingsService


def test_json_store_writes_atomically_and_versions(tmp_path):
    store = JsonStore(tmp_path / "s.json", 3, lambda: {})
    store.save({"a": 1})
    data = json.loads((tmp_path / "s.json").read_text())
    assert data == {"a": 1, "schema_version": 3}
    assert not (tmp_path / "s.json.tmp").exists()


def test_older_schema_is_quarantined(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"schema_version": 1, "x": 1}))
    assert JsonStore(path, 2, lambda: {"fresh": True}).load() == {"fresh": True}
    assert list(tmp_path.glob("s.json.corrupt-*"))


def test_settings_roundtrip_and_fallbacks(tmp_path):
    path = tmp_path / "settings.json"
    svc = SettingsService(path)
    target = tmp_path / "games"
    svc.set_library_dir(target)
    again = SettingsService(path)
    assert again.library_dir == target.resolve()
    path.write_text(json.dumps({"schema_version": 1, "library_dir": 42, "download_dir": ""}))
    broken = SettingsService(path)
    assert broken.settings.library_dir and broken.settings.download_dir


def test_translation_lookup_and_fallbacks():
    assert "Nolde" in t("app.name")
    assert t("does.not.exist") == "does.not.exist"
    assert t("discover.count", count=7) == "7 projects"
    assert available_locales() == ["en"]
