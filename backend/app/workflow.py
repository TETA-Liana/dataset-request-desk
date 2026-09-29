"""The request status workflow, in one place.

    submitted -> in_progress -> delivered -> accepted
                                          -> rejected -> in_progress (rework)

TRANSITIONS maps (from_status, to_status) to the roles allowed to make that move.
To add a new step you only add a line here.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, DatasetRequest, StatusChange, User

TRANSITIONS = {
    ("submitted", "in_progress"): {"operator", "admin"},
    ("in_progress", "delivered"): {"operator", "admin"},
    ("delivered", "accepted"): {"client"},
    ("delivered", "rejected"): {"client"},
    ("rejected", "in_progress"): {"operator", "admin"},
}

# Operators may only add or remove episodes while they are working on the request.
EDITABLE_STATUSES = {"in_progress"}


def allowed_next_statuses(request: DatasetRequest, user: User) -> list[str]:
    """Used by the UI to decide which buttons to show. The server still checks again."""
    return [to for (frm, to), roles in TRANSITIONS.items()
            if frm == request.status and user.role in roles
            and (user.role != "client" or request.client_id == user.id)]


def assigned_count(db: Session, request_id: int) -> int:
    return db.scalar(select(func.count()).where(Assignment.request_id == request_id))


def change_status(db: Session, request: DatasetRequest, new_status: str,
                  user: User, comment: str | None = None) -> DatasetRequest:
    move = (request.status, new_status)
    if move not in TRANSITIONS:
        raise HTTPException(409, f"Cannot move a request from {request.status} to {new_status}")
    if user.role not in TRANSITIONS[move]:
        raise HTTPException(403, f"A {user.role} cannot move a request to {new_status}")
    if user.role == "client" and request.client_id != user.id:
        raise HTTPException(404, "Request not found")

    if new_status == "delivered":
        count = assigned_count(db, request.id)
        if count < request.episodes_requested:
            raise HTTPException(
                409, f"Only {count} of {request.episodes_requested} episodes are assigned"
            )

    db.add(StatusChange(request_id=request.id, from_status=request.status,
                        to_status=new_status, changed_by_id=user.id, comment=comment))
    request.status = new_status
    db.commit()
    return request
