"""Diagnostics report for bug reports. Personal data is removed before anything is written:
the user's home folder and user name are replaced, and no tokens or file contents are included."""

from __future__ import annotations

import getpass
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..app.version import __version__


def redact(text: str) -> str:
    home = str(Path.home())
    text = text.replace(home, "~")
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no user name is also fine
        user = ""
    if user and len(user) > 2:
        text = text.replace(user, "<user>")
    return text


def build_report(services, log_path: Path, qt_version: str, log_lines: int = 200) -> str:
    lines = [
        "Nolde Launcher diagnostics",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Launcher version: {__version__}",
        f"Python: {sys.version.split()[0]}   Qt: {qt_version}",
        f"System: {platform.system()} {platform.release()} ({platform.machine()})",
        f"CPU cores: {_cpu_count()}",
        "",
        "Settings (values only):",
    ]
    for name, value in sorted(vars(services.settings.settings).items()):
        lines.append(f"  {name} = {redact(str(value))}")
    records = services.library.records()
    lines += ["", f"Installed games: {len(records)}"]
    for r in records:
        lines.append(f"  {r.project_id} version={r.installed_version or '-'} state={r.state} "
                     f"exe_set={bool(r.main_executable)} playtime_s={r.play_seconds}")
    snapshot_info = services.catalog.load_cached()
    if snapshot_info is None:
        lines.append("Catalog: no saved copy")
    else:
        when = datetime.fromtimestamp(snapshot_info.fetched_at, timezone.utc).isoformat() \
            if snapshot_info.fetched_at else "unknown"
        lines.append(f"Catalog: {len(snapshot_info.projects)} projects, saved {when}, "
                     f"{snapshot_info.skipped_entries} entries skipped")
    lines += ["", f"Last {log_lines} log lines:"]
    if log_path.exists():
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:]
        lines += [redact(line) for line in tail]
    else:
        lines.append("  (no log file yet)")
    return "\n".join(lines) + "\n"


def _cpu_count() -> int:
    import os
    return os.cpu_count() or 0
