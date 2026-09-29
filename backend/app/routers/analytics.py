"""Analytics. Every number is computed inside PostgreSQL with GROUP BY,
so we never load episodes into Python, however many there are."""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import STAFF, require_role
from app.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])

EPISODES_PER_DAY = text("""
    SELECT (recorded_at AT TIME ZONE 'UTC')::date AS day, robot_id, count(*) AS episodes
    FROM episodes
    WHERE recorded_at >= :start AND recorded_at < :end
    GROUP BY day, robot_id
    ORDER BY day, robot_id
""")

REQUESTS_BY_STATUS = text("""
    SELECT status, count(*) AS requests
    FROM dataset_requests
    WHERE created_at >= :start AND created_at < :end
    GROUP BY status
    ORDER BY status
""")

# "submitted" time is when the request was created. If a request was delivered,
# rejected and delivered again, we count the FIRST delivery.
MEDIAN_TIME_TO_DELIVERY = text("""
    WITH first_delivery AS (
        SELECT request_id, min(changed_at) AS delivered_at
        FROM status_changes
        WHERE to_status = 'delivered'
        GROUP BY request_id
    )
    SELECT
        count(*) AS delivered_requests,
        percentile_cont(0.5) WITHIN GROUP (
            ORDER BY extract(epoch FROM fd.delivered_at - r.created_at)
        ) AS median_seconds
    FROM dataset_requests r
    JOIN first_delivery fd ON fd.request_id = r.id
    WHERE r.created_at >= :start AND r.created_at < :end
""")

TOP_GOOD_TASKS = text("""
    SELECT task_name, count(*) AS good_episodes
    FROM episodes
    WHERE quality = 'good' AND recorded_at >= :start AND recorded_at < :end
    GROUP BY task_name
    ORDER BY good_episodes DESC, task_name
    LIMIT 5
""")


@router.get("")
def analytics(start: date, end: date, db: Session = Depends(get_db),
              _: User = Depends(require_role(*STAFF))):
    """Both dates are inclusive and read as UTC days: start=2026-08-01&end=2026-08-31."""
    if end < start:
        raise HTTPException(422, "end must be on or after start")

    params = {
        "start": datetime.combine(start, time.min, tzinfo=timezone.utc),
        "end": datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    }

    per_day = [dict(r._mapping) for r in db.execute(EPISODES_PER_DAY, params)]
    by_status = {r.status: r.requests for r in db.execute(REQUESTS_BY_STATUS, params)}
    delivery = db.execute(MEDIAN_TIME_TO_DELIVERY, params).one()
    top_tasks = [dict(r._mapping) for r in db.execute(TOP_GOOD_TASKS, params)]

    median = delivery.median_seconds
    return {
        "range": {"start": start, "end": end},
        "episodes_per_day_per_robot": per_day,
        "request_fulfilment": {
            "requests_by_status": by_status,
            "delivered_requests": delivery.delivered_requests,
            "median_hours_submitted_to_delivered": round(median / 3600, 2) if median is not None else None,
        },
        "top_tasks_by_good_episodes": top_tasks,
    }
