# Contributing

Thank you for helping. The launcher is written in Python with PySide6.

## Set up

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

## Before opening a pull request

```powershell
python -m pyflakes nolde_launcher tests main.py scripts
python -m pytest tests -q
```

Both must pass. CI runs the same two commands on Windows.

## Guidelines

- Interface text goes in `nolde_launcher/localization/en.json`. Do not hardcode text in widgets.
- Keep network, disk and process work off the UI thread (see `ui/workers.py`).
- Downloads, installs and launches must never run code automatically. Installation only extracts files.
- Add a test for each bug you fix.
- Do not commit personal paths, tokens or game files.

## Reporting security problems

See [SECURITY.md](SECURITY.md). Please do not open a public issue for them.
