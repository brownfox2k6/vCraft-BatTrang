"""Locale-aware currency and date/datetime formatting utilities for VI and EN."""

from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.i18n import DEFAULT_LANG, normalize_lang

_EN_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _resolve_vietnam_tz() -> tzinfo:
    try:
        return ZoneInfo("Asia/Ho_Chi_Minh")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=7))


VIETNAM_TZ: tzinfo = _resolve_vietnam_tz()


def _to_vietnam_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(VIETNAM_TZ)


def format_currency(amount: int | float | Decimal, lang: str = DEFAULT_LANG) -> str:
    """Format a VND amount according to VI (`48.000 đ`) or EN (`48,000 VND`) conventions."""
    resolved = normalize_lang(lang)
    decimal_amount = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    whole = int(decimal_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    grouped = f"{whole:,}"
    if resolved == "en":
        return f"{grouped} VND"
    return f"{grouped.replace(',', '.')} đ"


def format_date(value: date | datetime, lang: str = DEFAULT_LANG) -> str:
    """Format a date (or datetime) as `DD/MM/YYYY` (VI) or `Mon D, YYYY` (EN)."""
    resolved = normalize_lang(lang)
    target = _to_vietnam_datetime(value) if isinstance(value, datetime) else value
    if resolved == "en":
        month_name = _EN_MONTH_ABBR[target.month - 1]
        return f"{month_name} {target.day}, {target.year:04d}"
    return f"{target.day:02d}/{target.month:02d}/{target.year:04d}"


def format_datetime(value: datetime, lang: str = DEFAULT_LANG) -> str:
    """Format a datetime in Vietnam time as `DD/MM/YYYY HH:MM` (VI) or `Mon D, YYYY, HH:MM` (EN)."""
    resolved = normalize_lang(lang)
    local_dt = _to_vietnam_datetime(value)
    date_part = format_date(local_dt, resolved)
    time_part = f"{local_dt.hour:02d}:{local_dt.minute:02d}"
    if resolved == "en":
        return f"{date_part}, {time_part}"
    return f"{date_part} {time_part}"
