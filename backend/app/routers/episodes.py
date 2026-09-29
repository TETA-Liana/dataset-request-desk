import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import STAFF, require_role
from app.importer import import_episodes
from app.models import Assignment, Episode, User
from app.schemas import EpisodeOut

router = APIRouter(prefix="/episodes", tags=["episodes"])
log = logging.getLogger("app.import")
staff_only = require_role(*STAFF)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.get("")
def list_episodes(
    task_name: str | None = None,
    quality: str | None = Query(default=None, pattern="^(good|usable|bad)$"),
    robot_id: str | None = None,
    unassigned_only: bool = False,
    assignable_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
):
    query = (select(Episode, Assignment.request_id)
             .outerjoin(Assignment, Assignment.episode_id == Episode.episode_id))
    if task_name:
        query = query.where(Episode.task_name == task_name.strip().lower())
    if quality:
        query = query.where(Episode.quality == quality)
    if robot_id:
        query = query.where(Episode.robot_id == robot_id.strip().lower())
    if assignable_only:
        query = query.where(Episode.quality.in_(["good", "usable"]))
    if unassigned_only:
        query = query.where(Assignment.id.is_(None))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Episode.recorded_at.desc(), Episode.episode_id)
                      .limit(limit).offset(offset)).all()
    items = [EpisodeOut.model_validate(e).model_copy(update={"assigned_request_id": req_id})
             for e, req_id in rows]
    return {"total": total, "items": items}


@router.get("/task-names", response_model=list[str])
def task_names(db: Session = Depends(get_db), _: User = Depends(staff_only)):
    """Distinct task names, for the filter dropdown in the UI."""
    return db.scalars(select(Episode.task_name).distinct().order_by(Episode.task_name)).all()


@router.post("/import")
async def import_csv(file: UploadFile, db: Session = Depends(get_db),
                     user: User = Depends(staff_only)):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 50 MB")
    try:
        text = content.decode("utf-8-sig")  # utf-8-sig also strips an Excel BOM if present
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 encoded CSV")

    try:
        report = import_episodes(db, io.StringIO(text, newline=""))
    except ValueError as e:
        raise HTTPException(400, str(e))

    log.info("episode import finished", extra={"fields": {
        "user_id": user.id, "file_name": file.filename, "rows_read": report["rows_read"],
        "imported": report["imported"], "skipped": report["skipped"],
    }})
    return report
