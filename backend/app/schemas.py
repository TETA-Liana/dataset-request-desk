"""Shapes of what the API accepts and returns. Pydantic validates input for us."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    organisation: str | None
    role: str
    is_active: bool


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(client|operator|admin)$")
    organisation: str | None = Field(default=None, max_length=255)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(client|operator|admin)$")
    is_active: bool | None = None


class RequestCreate(BaseModel):
    task_name: str = Field(min_length=1, max_length=255)
    episodes_requested: int = Field(gt=0, le=100_000)
    deadline: date
    notes: str | None = Field(default=None, max_length=5000)


class StatusChangeIn(BaseModel):
    status: str
    comment: str | None = Field(default=None, max_length=2000)


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    changed_at: datetime
    changed_by_name: str
    comment: str | None


class RequestOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    task_name: str
    episodes_requested: int
    episodes_assigned: int
    deadline: date
    notes: str | None
    status: str
    created_at: datetime
    allowed_next: list[str]


class RequestDetailOut(RequestOut):
    history: list[HistoryOut]


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int
    operator_name: str | None
    quality: str
    assigned_request_id: int | None = None


class AssignIn(BaseModel):
    episode_ids: list[str] = Field(min_length=1, max_length=1000)
