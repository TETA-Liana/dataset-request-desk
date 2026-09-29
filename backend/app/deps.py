"""Auth dependencies. Every protected route uses one of these, so the check
happens on the server no matter what the UI shows or hides."""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import read_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Not logged in")

    user_id = read_token(creds.credentials)
    # We load the user from the database on every request (instead of trusting
    # the role inside the token) so that deactivating a user or changing their
    # role takes effect immediately.
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(401, "Invalid or expired token")

    request.state.user_id = user.id  # picked up by the logging middleware
    return user


def require_role(*roles: str):
    """Usage: user: User = Depends(require_role("operator", "admin"))"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Your role is not allowed to do this")
        return user
    return checker


STAFF = ("operator", "admin")  # admin can do everything an operator can
