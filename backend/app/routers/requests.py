"""Dataset requests, their status workflow, and episode assignments."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import STAFF, get_current_user, require_role
from app.models import Assignment, DatasetRequest, Episode, StatusChange, User
from app.schemas import (
    AssignIn, EpisodeOut, HistoryOut, RequestCreate, RequestDetailOut, RequestOut, StatusChangeIn,
)
from app.workflow import EDITABLE_STATUSES, allowed_next_statuses, change_status

router = APIRouter(prefix="/requests", tags=["requests"])
ASSIGNABLE_QUALITIES = {"good", "usable"}


def load_request(db: Session, request_id: int, user: User, lock: bool = False) -> DatasetRequest:
    """Fetch a request the user is allowed to see.

    A client asking for someone else's request gets 404, not 403, so they
    cannot even find out that the request exists.
    lock=True takes a row lock (SELECT ... FOR UPDATE) so two people changing
    the same request at the same moment are handled one after the other.
    """
    query = select(DatasetRequest).where(DatasetRequest.id == request_id)
    if lock:
        query = query.with_for_update()
    request = db.scalar(query)
    if request is None or (user.role == "client" and request.client_id != user.id):
        raise HTTPException(404, "Request not found")
    return request


def to_out(request: DatasetRequest, assigned: int, user: User) -> dict:
    return {
        "id": request.id,
        "client_id": request.client_id,
        "client_name": request.client.name,
        "task_name": request.task_name,
        "episodes_requested": request.episodes_requested,
        "episodes_assigned": assigned,
        "deadline": request.deadline,
        "notes": request.notes,
        "status": request.status,
        "created_at": request.created_at,
        "allowed_next": allowed_next_statuses(request, user),
    }


def to_detail(db: Session, request: DatasetRequest, user: User) -> dict:
    db.refresh(request)
    assigned = db.scalar(select(func.count()).where(Assignment.request_id == request.id))
    history = [
        HistoryOut(from_status=h.from_status, to_status=h.to_status, changed_at=h.changed_at,
                   changed_by_name=h.changed_by.name, comment=h.comment)
        for h in request.history
    ]
    return {**to_out(request, assigned, user), "history": history}


@router.get("", response_model=list[RequestOut])
def list_requests(status: str | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    # Count assignments in one grouped query instead of one query per request.
    counts = (select(Assignment.request_id, func.count().label("n"))
              .group_by(Assignment.request_id).subquery())
    query = (select(DatasetRequest, func.coalesce(counts.c.n, 0))
             .outerjoin(counts, counts.c.request_id == DatasetRequest.id)
             .options(selectinload(DatasetRequest.client))
             .order_by(DatasetRequest.created_at.desc()))

    if user.role == "client":
        query = query.where(DatasetRequest.client_id == user.id)
    if status:
        query = query.where(DatasetRequest.status == status)

    return [to_out(r, n, user) for r, n in db.execute(query).all()]


@router.post("", response_model=RequestDetailOut, status_code=201)
def create_request(body: RequestCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_role("client"))):
    if body.deadline < date.today():
        raise HTTPException(422, "Deadline cannot be in the past")

    request = DatasetRequest(client_id=user.id, task_name=body.task_name.strip(),
                             episodes_requested=body.episodes_requested,
                             deadline=body.deadline, notes=body.notes, status="submitted")
    db.add(request)
    db.flush()  # gives us request.id before we write the first history row
    db.add(StatusChange(request_id=request.id, from_status=None,
                        to_status="submitted", changed_by_id=user.id))
    db.commit()
    return to_detail(db, request, user)


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(request_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return to_detail(db, load_request(db, request_id, user), user)


@router.post("/{request_id}/status", response_model=RequestDetailOut)
def update_status(request_id: int, body: StatusChangeIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    request = load_request(db, request_id, user, lock=True)
    change_status(db, request, body.status, user, body.comment)
    return to_detail(db, request, user)


@router.get("/{request_id}/assignments", response_model=list[EpisodeOut])
def list_assignments(request_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    load_request(db, request_id, user)  # the client may see what was delivered to them
    episodes = db.scalars(
        select(Episode).join(Assignment, Assignment.episode_id == Episode.episode_id)
        .where(Assignment.request_id == request_id).order_by(Episode.episode_id)
    ).all()
    return [EpisodeOut.model_validate(e).model_copy(update={"assigned_request_id": request_id})
            for e in episodes]


@router.post("/{request_id}/assignments", status_code=201)
def assign_episodes(request_id: int, body: AssignIn, db: Session = Depends(get_db),
                    user: User = Depends(require_role(*STAFF))):
    request = load_request(db, request_id, user, lock=True)
    if request.status not in EDITABLE_STATUSES:
        raise HTTPException(409, f"Episodes can only be assigned while the request is in_progress "
                                 f"(it is {request.status})")

    wanted = list(dict.fromkeys(e.strip().upper() for e in body.episode_ids))  # dedupe, keep order
    episodes = {e.episode_id: e for e in db.scalars(select(Episode).where(Episode.episode_id.in_(wanted)))}
    taken = dict(db.execute(select(Assignment.episode_id, Assignment.request_id)
                            .where(Assignment.episode_id.in_(wanted))).all())

    # Check everything first. We assign all of them or none of them, so the
    # operator never ends up with a half-done batch.
    problems = []
    for episode_id in wanted:
        episode = episodes.get(episode_id)
        if episode is None:
            problems.append(f"{episode_id}: does not exist")
        elif episode.quality not in ASSIGNABLE_QUALITIES:
            problems.append(f"{episode_id}: quality is {episode.quality}, only good or usable allowed")
        elif episode_id in taken:
            problems.append(f"{episode_id}: already assigned to request {taken[episode_id]}")
    if problems:
        raise HTTPException(409, {"message": "No episodes were assigned", "problems": problems})

    for episode_id in wanted:
        db.add(Assignment(episode_id=episode_id, request_id=request.id, assigned_by_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        # Someone else assigned one of these episodes between our check and our insert.
        # The UNIQUE constraint on assignments.episode_id caught it.
        db.rollback()
        raise HTTPException(409, "One of these episodes was just assigned by someone else, try again")

    return {"assigned": wanted}


@router.delete("/{request_id}/assignments/{episode_id}", status_code=204)
def unassign_episode(request_id: int, episode_id: str, db: Session = Depends(get_db),
                     user: User = Depends(require_role(*STAFF))):
    request = load_request(db, request_id, user, lock=True)
    if request.status not in EDITABLE_STATUSES:
        raise HTTPException(409, "Episodes can only be removed while the request is in_progress")

    assignment = db.scalar(select(Assignment).where(Assignment.request_id == request_id,
                                                    Assignment.episode_id == episode_id.upper()))
    if assignment is None:
        raise HTTPException(404, "That episode is not assigned to this request")
    db.delete(assignment)
    db.commit()
