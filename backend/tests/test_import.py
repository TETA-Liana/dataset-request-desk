"""CSV import: cleaning rules, reporting, and above all idempotency."""
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.importer import RowError, import_episodes, parse_row
from app.models import Episode

SEED_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "seed", "episodes.csv")
HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality"


def row(**overrides):
    values = {"episode_id": "EP-00001", "robot_id": "arm-01", "task_name": "pick cup",
              "recorded_at": "2026-08-01T10:00:00", "duration_seconds": "30",
              "operator_name": "Eric", "quality": "good"}
    values.update(overrides)
    return list(values.values())


def run_import(db, *lines):
    return import_episodes(db, [HEADER, *lines])


def episode_count(db):
    return db.scalar(select(func.count()).select_from(Episode))


# ---- cleaning single rows ----

def test_values_are_normalised():
    clean = parse_row(row(episode_id=" ep-00001 ", robot_id=" ARM-01", task_name="  Pick   Cup ",
                          quality="USABLE", operator_name="  Eric "))
    assert clean["episode_id"] == "EP-00001"
    assert clean["robot_id"] == "arm-01"
    assert clean["task_name"] == "pick cup"
    assert clean["quality"] == "usable"
    assert clean["operator_name"] == "Eric"


@pytest.mark.parametrize("value", [
    "2026-08-14T09:15:00", "2026-08-14 09:15:00", "2026-08-14T09:15:00Z", "14/08/2026 09:15",
])
def test_known_date_formats_are_accepted(value):
    assert parse_row(row(recorded_at=value))["recorded_at"] == \
        datetime(2026, 8, 14, 9, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("field,value,reason", [
    ("episode_id", "", "missing_episode_id"),
    ("episode_id", "123", "invalid_episode_id"),
    ("robot_id", "", "missing_robot_id"),
    ("robot_id", "arm-99", "unknown_robot"),
    ("task_name", "   ", "missing_task_name"),
    ("recorded_at", "not a date", "invalid_recorded_at"),
    ("duration_seconds", "", "invalid_duration"),
    ("duration_seconds", "N/A", "invalid_duration"),
    ("duration_seconds", "-5", "invalid_duration"),
    ("duration_seconds", "45.5", "invalid_duration"),
    ("duration_seconds", "0", "invalid_duration"),
    ("duration_seconds", "999999", "invalid_duration"),
    ("quality", "", "invalid_quality"),
    ("quality", "excellent", "invalid_quality"),
])
def test_bad_values_are_rejected_with_a_reason(field, value, reason):
    with pytest.raises(RowError) as err:
        parse_row(row(**{field: value}))
    assert err.value.reason == reason


def test_wrong_column_count_is_malformed():
    with pytest.raises(RowError) as err:
        parse_row(["EP-00001", "arm-01", "pick cup"])
    assert err.value.reason == "malformed_row"


def test_missing_operator_is_imported_with_warning(db):
    report = run_import(db, ",".join(row(operator_name="")))
    assert report["imported"] == 1
    assert report["warnings"][0]["episode_id"] == "EP-00001"


def test_wrong_header_is_refused(db):
    with pytest.raises(ValueError):
        import_episodes(db, ["id,robot", "EP-1,arm-01"])


# ---- duplicates ----

def test_exact_duplicate_in_file_is_imported_once(db):
    line = ",".join(row())
    report = run_import(db, line, line)
    assert report["imported"] == 1
    assert report["skipped_by_reason"] == {"duplicate_in_file": 1}


def test_conflicting_duplicate_keeps_first_and_reports_second(db):
    report = run_import(db, ",".join(row(quality="bad")), ",".join(row(quality="good")))
    assert report["imported"] == 1
    assert report["skipped_by_reason"] == {"conflicting_duplicate_in_file": 1}
    assert db.get(Episode, "EP-00001").quality == "bad"


def test_ids_differing_only_in_case_are_the_same_episode(db):
    report = run_import(db, ",".join(row(episode_id="EP-00001")), ",".join(row(episode_id="ep-00001")))
    assert report["imported"] == 1


# ---- idempotency ----

def test_seed_file_import_is_idempotent(db):
    with open(SEED_CSV, newline="", encoding="utf-8-sig") as f:
        first = import_episodes(db, f)
    count_after_first = episode_count(db)

    with open(SEED_CSV, newline="", encoding="utf-8-sig") as f:
        second = import_episodes(db, f)

    assert first["imported"] > 0
    assert first["imported"] == count_after_first
    assert second["imported"] == 0
    assert episode_count(db) == count_after_first
    assert second["skipped_by_reason"]["already_imported"] == first["imported"]
    # the report explains every non-imported row
    assert first["rows_read"] == first["imported"] + first["skipped"]


def test_seed_file_report_catches_the_known_problems(db):
    with open(SEED_CSV, newline="", encoding="utf-8-sig") as f:
        report = import_episodes(db, f)
    reasons = report["skipped_by_reason"]
    for expected in ["unknown_robot", "malformed_row", "invalid_duration", "invalid_quality",
                     "invalid_recorded_at", "missing_episode_id", "duplicate_in_file",
                     "conflicting_duplicate_in_file", "blank_line"]:
        assert expected in reasons, expected


def test_existing_episode_is_never_overwritten(db):
    run_import(db, ",".join(row(quality="good")))
    report = run_import(db, ",".join(row(quality="bad")))
    assert report["imported"] == 0
    assert report["skipped_by_reason"] == {"conflicts_with_existing": 1}
    assert db.get(Episode, "EP-00001").quality == "good"


def test_new_rows_in_a_later_file_are_added(db):
    run_import(db, ",".join(row(episode_id="EP-00001")))
    report = run_import(db, ",".join(row(episode_id="EP-00001")), ",".join(row(episode_id="EP-00002")))
    assert report["imported"] == 1
    assert episode_count(db) == 2


# ---- the HTTP endpoint ----

def test_upload_endpoint(api, login, make_user):
    headers = login(make_user("operator"))
    with open(SEED_CSV, "rb") as f:
        first = api.post("/episodes/import", headers=headers, files={"file": ("e.csv", f, "text/csv")})
    with open(SEED_CSV, "rb") as f:
        second = api.post("/episodes/import", headers=headers, files={"file": ("e.csv", f, "text/csv")})
    assert first.status_code == 200 and first.json()["imported"] > 0
    assert second.json()["imported"] == 0


def test_upload_rejects_non_csv(api, login, make_user):
    headers = login(make_user("operator"))
    res = api.post("/episodes/import", headers=headers,
                   files={"file": ("x.bin", b"\xff\xfe\x00garbage", "application/octet-stream")})
    assert res.status_code == 400
