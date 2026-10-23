"""Human-readable times and sizes, translated through the string catalog."""

from __future__ import annotations

from datetime import datetime, timezone

from ..localization.i18n import t


def time_ago(iso: str) -> str:
    if not iso:
        return t("time.never")
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return t("time.never")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = max(0, (datetime.now(timezone.utc) - when).total_seconds())
    if seconds < 90:
        return t("time.just_now")
    minutes = int(seconds // 60)
    if minutes < 60:
        return t("time.minutes_ago", n=minutes)
    hours = minutes // 60
    if hours < 24:
        return t("time.hours_ago", n=hours)
    return t("time.days_ago", n=hours // 24)


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
