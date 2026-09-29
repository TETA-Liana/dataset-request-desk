"""Analytics: the numbers are right and the date range is respected."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.models import DatasetRequest, StatusChange


def at(day, hour=10):
    return datetime(2026, 8, day, hour, tzinfo=timezone.utc)


def get(api, headers, start="2026-08-01", end="2026-08-31"):
    res = api.get(f"/analytics?start={start}&end={end}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_episodes_per_day_per_robot(api, login, make_user, make_episode):
    make_episode(robot_id="arm-01", recorded_at=at(1, 9))
    make_episode(robot_id="arm-01", recorded_at=at(1, 23))
    make_episode(robot_id="arm-02", recorded_at=at(1))
    make_episode(robot_id="arm-01", recorded_at=at(2))
    make_episode(robot_id="arm-01", recorded_at=datetime(2026, 9, 5, tzinfo=timezone.utc))  # outside

    data = get(api, login(make_user("operator")))
    assert data["episodes_per_day_per_robot"] == [
        {"day": "2026-08-01", "robot_id": "arm-01", "episodes": 2},
        {"day": "2026-08-01", "robot_id": "arm-02", "episodes": 1},
        {"day": "2026-08-02", "robot_id": "arm-01", "episodes": 1},
    ]


def test_end_date_is_inclusive(api, login, make_user, make_episode):
    make_episode(recorded_at=datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc))
    data = get(api, login(make_user("operator")), end="2026-08-31")
    assert sum(r["episodes"] for r in data["episodes_per_day_per_robot"]) == 1


def test_top_tasks_counts_only_good_episodes(api, login, make_user, make_episode):
    for _ in range(3):
        make_episode(task_name="pour water")
    for _ in range(2):
        make_episode(task_name="pick cup")
    for _ in range(5):
        make_episode(task_name="fold towel", quality="usable")  # not good, must not count

    top = get(api, login(make_user("operator")))["top_tasks_by_good_episodes"]
    assert top == [{"task_name": "pour water", "good_episodes": 3},
                   {"task_name": "pick cup", "good_episodes": 2}]


def test_top_tasks_returns_at_most_five(api, login, make_user, make_episode):
    for i in range(7):
        make_episode(task_name=f"task {i}")
    assert len(get(api, login(make_user("operator")))["top_tasks_by_good_episodes"]) == 5


def test_request_status_counts_and_median(api, db, login, make_user, new_request, move,
                                          assign, make_episode):
    client, operator = make_user("client"), make_user("operator")
    hours_to_deliver = [2, 10, 4]  # median should be 4
    for hours in hours_to_deliver:
        req = new_request(client, count=1)
        move(operator, req["id"], "in_progress")
        assign(operator, req["id"], make_episode())
        move(operator, req["id"], "delivered")
        # rewrite timestamps so the durations are known
        created = at(10)
        db.execute(update(DatasetRequest).where(DatasetRequest.id == req["id"]).values(created_at=created))
        db.execute(update(StatusChange).where(StatusChange.request_id == req["id"],
                                              StatusChange.to_status == "delivered")
                   .values(changed_at=created + timedelta(hours=hours)))
    still_open = new_request(client)
    db.execute(update(DatasetRequest).where(DatasetRequest.id == still_open["id"]).values(created_at=at(11)))
    db.commit()

    fulfilment = get(api, login(operator))["request_fulfilment"]
    assert fulfilment["requests_by_status"] == {"delivered": 3, "submitted": 1}
    assert fulfilment["delivered_requests"] == 3
    assert fulfilment["median_hours_submitted_to_delivered"] == 4.0


def test_empty_range_and_bad_range(api, login, make_user):
    headers = login(make_user("operator"))
    data = get(api, headers, start="2020-01-01", end="2020-01-02")
    assert data["episodes_per_day_per_robot"] == []
    assert data["request_fulfilment"]["median_hours_submitted_to_delivered"] is None
    assert api.get("/analytics?start=2026-08-02&end=2026-08-01", headers=headers).status_code == 422
