"""
Current Date Tool.

Returns the current system date and time.

This module is completely independent of FastMCP.
"""

from __future__ import annotations

from datetime import datetime


def current_date() -> dict:
    """
    Return the current system date and time.

    The values are obtained directly from the operating system clock.
    """

    now = datetime.now()

    return {
        "success": True,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
        "month": now.strftime("%B"),
        "year": now.year,
        "iso_datetime": now.isoformat(timespec="seconds"),
        "unix_timestamp": int(now.timestamp()),
    }