"""Helper functions."""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import List

DEFAULT_SKIP_DAYS = [5, 6]  # Saturday and Sunday

def get_skip_dates(skip_dates) -> List[datetime]:
    """Get list of dates on which there are no events."""
    dates = set()  # Start as set to avoid duplicates

    skip_dates = skip_dates or []
    # self.log(skip_dates)
    for value in skip_dates:
        rangePos = value.find("-")

        if rangePos == -1:
            # self.log(datetime.strptime(value, "%m/%d/%Y").date())
            dates.add(datetime.strptime(value, "%m/%d/%Y").date())
        else:
            ranges = value.split("-")
            start_date = datetime.strptime(ranges[0], "%m/%d/%Y")
            end_date = datetime.strptime(ranges[1], "%m/%d/%Y")
            day_delta = timedelta(days=1)

            while start_date <= end_date:
                dates.add(start_date.date())
                start_date += day_delta

    values = list(dates)
    values.sort()
    return values


def to_float(value) -> float:
    """Safely convert into float value."""
    try:
        return float(value)
    except:  # noqa: E722
        return 0


def round_float(value: float | None, decimal_places: int) -> float | None:
    """Return formatted value based on decimal_places."""
    if value is None:
        return None

    if decimal_places < 0:
        return value
    if decimal_places == 0:
        return int(value)

    return round(value, decimal_places)
