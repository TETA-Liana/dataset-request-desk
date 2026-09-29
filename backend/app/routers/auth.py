from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginIn, LoginOut, UserOut
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Used when the email does not exist, so a wrong email takes as long as a wrong
# password. Otherwise an attacker could time responses to find real emails.
DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)

    # One message for every failure, so we do not reveal which part was wrong.
    if not user or not password_ok or not user.is_active:
        raise HTTPException(401, "Wrong email or password")

    return LoginOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
