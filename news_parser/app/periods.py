from datetime import datetime, timedelta, timezone

from app.config import Period


def period_bounds(period: Period, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    if period == "day":
        start = end - timedelta(days=1)
    elif period == "week":
        start = end - timedelta(days=7)
    else:
        start = end - timedelta(days=30)

    return start, end
