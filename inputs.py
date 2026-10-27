"""Validation shared by the file pipeline and local tool interfaces."""
from datetime import date


def iso_date(value, field="date"):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid date in YYYY-MM-DD format") from exc
    if result.isoformat() != value:
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format")
    return result


def ticker(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Ticker must be a nonempty string")
    return value.strip().upper()
