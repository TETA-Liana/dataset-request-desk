"""Episode CSV import.

The recording system's export is messy, so the import works in two steps:

1. parse_row() cleans and validates ONE row. It either returns a clean dict
   or raises RowError with a short reason code. It never touches the database,
   which makes it easy to test.
2. import_episodes() runs every row through parse_row(), removes duplicates,
   compares against what is already in the database, and inserts only new
   episodes. Nothing that already exists is ever overwritten.

Running the same file twice is safe: the second run imports 0 rows and reports
every row as "already_imported".
"""
import csv
import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Episode

COLUMNS = ["episode_id", "robot_id", "task_name", "recorded_at",
           "duration_seconds", "operator_name", "quality"]

# From seed/README.md. In a real system this would be a robots table.
KNOWN_ROBOTS = {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"}

QUALITIES = {"good", "usable", "bad"}

# Episodes are short clips. Anything over an hour is almost certainly a bad value.
MAX_DURATION_SECONDS = 3600

# Formats we have seen in the export. Order matters only for readability.
DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",   # 2026-08-14T09:20:00 (the normal one)
    "%Y-%m-%d %H:%M:%S",   # 2026-08-14 09:12:00
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M",      # 14/08/2026 09:15 (day first, as used in Rwanda)
    "%d/%m/%Y %H:%M:%S",
]

EPISODE_ID_PATTERN = re.compile(r"^EP-\d+$")

# We only return this many skipped rows in the report so a huge broken file
# does not produce a huge response. The counts are always complete.
MAX_REPORTED_ROWS = 500

BATCH_SIZE = 1000


class RowError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def clean_text(value: str) -> str:
    """Trim and collapse repeated spaces: '  Pick   Cup ' -> 'Pick Cup'."""
    return " ".join(value.split())


def parse_date(value: str) -> datetime:
    value = value.strip()
    # A trailing Z means UTC, which is what we assume anyway.
    if value.endswith("Z"):
        value = value[:-1]
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        # The export has no timezone info, so we treat every time as UTC.
        return parsed.replace(tzinfo=timezone.utc)
    raise RowError("invalid_recorded_at", f"could not read date {value!r}")


def parse_duration(value: str) -> int:
    value = value.strip()
    if not value.isdigit():  # rejects "", "N/A", "-5" and "45.5"
        raise RowError("invalid_duration", f"{value!r} is not a whole number of seconds")
    seconds = int(value)
    if seconds < 1 or seconds > MAX_DURATION_SECONDS:
        raise RowError("invalid_duration", f"{seconds}s is outside 1..{MAX_DURATION_SECONDS}")
    return seconds


def parse_row(fields: list[str]) -> dict:
    if len(fields) != len(COLUMNS):
        raise RowError("malformed_row", f"expected {len(COLUMNS)} columns, got {len(fields)}")

    raw = dict(zip(COLUMNS, fields))

    episode_id = raw["episode_id"].strip().upper()
    if not episode_id:
        raise RowError("missing_episode_id")
    if not EPISODE_ID_PATTERN.match(episode_id):
        raise RowError("invalid_episode_id", f"{episode_id!r}")

    robot_id = raw["robot_id"].strip().lower()
    if not robot_id:
        raise RowError("missing_robot_id")
    if robot_id not in KNOWN_ROBOTS:
        raise RowError("unknown_robot", f"{robot_id!r}")

    task_name = clean_text(raw["task_name"]).lower()
    if not task_name:
        raise RowError("missing_task_name")

    quality = raw["quality"].strip().lower()
    if quality not in QUALITIES:
        raise RowError("invalid_quality", f"{raw['quality']!r}")

    return {
        "episode_id": episode_id,
        "robot_id": robot_id,
        "task_name": task_name,
        "recorded_at": parse_date(raw["recorded_at"]),
        "duration_seconds": parse_duration(raw["duration_seconds"]),
        # Operator name is informational only, so a missing one is allowed.
        "operator_name": clean_text(raw["operator_name"]) or None,
        "quality": quality,
    }


def same_episode(existing: Episode, row: dict) -> bool:
    return all(getattr(existing, key) == value for key, value in row.items())


def import_episodes(db: Session, lines) -> dict:
    """`lines` is anything csv.reader accepts: an open text file or a list of strings."""
    reader = csv.reader(lines)

    header = [h.strip().lower() for h in next(reader, [])]
    if header != COLUMNS:
        raise ValueError(f"CSV header must be exactly: {','.join(COLUMNS)}")

    rows_read = 0
    skipped = []
    warnings = []
    valid = {}  # episode_id -> (line number, clean row)

    def skip(line, episode_id, reason, detail=""):
        skipped.append({"line": line, "episode_id": episode_id,
                        "reason": reason, "detail": detail})

    # Step 1: clean every row and drop duplicates inside the file itself.
    for fields in reader:
        line = reader.line_num
        if not any(f.strip() for f in fields):
            skip(line, None, "blank_line")
            continue
        rows_read += 1

        try:
            row = parse_row(fields)
        except RowError as e:
            episode_id = fields[0].strip().upper() if fields and fields[0].strip() else None
            skip(line, episode_id, e.reason, e.detail)
            continue

        episode_id = row["episode_id"]
        if episode_id in valid:
            first_line, first_row = valid[episode_id]
            if first_row == row:
                skip(line, episode_id, "duplicate_in_file", f"same as line {first_line}")
            else:
                # We cannot know which version is correct, so we keep the first
                # one and make the conflict visible instead of guessing.
                skip(line, episode_id, "conflicting_duplicate_in_file",
                     f"differs from line {first_line}, kept line {first_line}")
            continue

        if row["operator_name"] is None:
            warnings.append({"line": line, "episode_id": episode_id,
                             "warning": "missing operator_name, imported anyway"})
        valid[episode_id] = (line, row)

    # Step 2: compare with the database in batches and insert only new episodes.
    imported = 0
    ids = list(valid)
    for start in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[start:start + BATCH_SIZE]
        existing = {
            e.episode_id: e
            for e in db.scalars(select(Episode).where(Episode.episode_id.in_(batch_ids)))
        }

        new_rows = []
        for episode_id in batch_ids:
            line, row = valid[episode_id]
            if episode_id not in existing:
                new_rows.append(row)
            elif same_episode(existing[episode_id], row):
                skip(line, episode_id, "already_imported")
            else:
                # Never overwrite: the episode may already be delivered to a client.
                skip(line, episode_id, "conflicts_with_existing",
                     "database has different values for this episode, not overwritten")

        if new_rows:
            # ON CONFLICT DO NOTHING protects us if two imports run at the same time.
            # RETURNING tells us which rows were really inserted.
            stmt = (insert(Episode).values(new_rows)
                    .on_conflict_do_nothing(index_elements=["episode_id"])
                    .returning(Episode.episode_id))
            inserted = set(db.scalars(stmt))
            imported += len(inserted)
            for row in new_rows:
                if row["episode_id"] not in inserted:
                    skip(valid[row["episode_id"]][0], row["episode_id"], "already_imported")

    db.commit()

    skipped.sort(key=lambda s: s["line"])
    return {
        "rows_read": rows_read,
        "imported": imported,
        "skipped": len([s for s in skipped if s["reason"] != "blank_line"]),
        "skipped_by_reason": dict(Counter(s["reason"] for s in skipped)),
        "skipped_rows": skipped[:MAX_REPORTED_ROWS],
        "warnings": warnings[:MAX_REPORTED_ROWS],
    }
