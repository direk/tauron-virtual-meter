"""Pure conversion of Tauron profiles; never replace missing energy with zero."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
UTC = timezone.utc


class ProfileError(ValueError):
    """An interval cannot be positioned without guessing."""


def energy(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).replace(",", "."))
    except InvalidOperation as err:
        raise ProfileError("Invalid energy value") from err
    if not result.is_finite() or result < 0:
        raise ProfileError("Invalid energy value")
    return result


def day_hours(day: date):
    start = datetime.combine(day, time(), WARSAW).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(), WARSAW).astimezone(UTC)
    return [start + timedelta(hours=i) for i in range(int((end - start).total_seconds() / 3600))]


def parse_day(day: date, response: dict):
    """Return UTC start -> kWh strings, preserving exact decimals.

    Upstream interprets Hour 1 as 00:00–01:00. On DST days, accept only
    complete sequential 1..23/25 arrays or explicit repeated/skipped wall hours.
    Ambiguous 24-slot DST responses are retained raw, never guessed.

    The caller requests exactly one day (from == to). As in Tauron AMIplus,
    use that requested day, not allData.Date: the latter can describe a
    different date/format even for a correctly scoped daily response.
    """
    data = response.get("data")
    if not isinstance(data, dict):
        raise ProfileError("Unexpected profile data")
    hours = day_hours(day)
    rows = data.get("allData")
    if rows is None or (rows == [] and data.get("values")):
        values = data.get("values")
        if values is None:
            raise ProfileError("No recognized interval array")
        if not values:
            return {}
        if len(values) != len(hours):
            raise ProfileError("Unknown profile resolution or ambiguous DST day")
        return {
            stamp.isoformat(): str(value)
            for stamp, raw in zip(hours, values, strict=True)
            if (value := energy(raw)) is not None
        }
    if not isinstance(rows, list):
        raise ProfileError("Unexpected allData type")
    if not rows:
        return {}
    if any(not isinstance(row, dict) for row in rows):
        raise ProfileError("Invalid interval row")
    try:
        labels = [int(row["Hour"]) for row in rows]
    except (KeyError, TypeError, ValueError) as err:
        raise ProfileError("Unrecognized hour labels") from err
    if len(hours) != 24:
        if len(rows) != len(hours):
            raise ProfileError("Incomplete or ambiguous DST day")
        sequential = list(range(1, len(hours) + 1))
        wall = [stamp.astimezone(WARSAW).hour + 1 for stamp in hours]
        if labels not in (sequential, wall):
            raise ProfileError("Unrecognized DST hour numbering")
        stamps = hours
    else:
        if any(label < 1 or label > 24 for label in labels) or max(Counter(labels).values()) > 1:
            raise ProfileError("Duplicate hours or unknown sub-hourly resolution")
        stamps = [hours[label - 1] for label in labels]
    return {
        stamp.isoformat(): str(value)
        for stamp, row in zip(stamps, rows, strict=True)
        if "Status" not in row or row["Status"] is not None
        if (value := energy(row.get("EC"))) is not None
    }


def cumulative_statistics(profiles: dict):
    """Recompute all following sums when old values change or are backfilled.

    The counter is virtual (zero before the oldest available interval),
    not a reconstruction of the physical meter's register.
    """
    intervals = {}
    for values in profiles.values():
        intervals.update(values)
    total = Decimal(0)
    result = []
    for timestamp, raw in sorted(intervals.items()):
        total += Decimal(raw)
        result.append({"start": datetime.fromisoformat(timestamp),
                       "state": float(total), "sum": float(total)})
    return result
