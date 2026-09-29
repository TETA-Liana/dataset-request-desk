"""Creates the seed users and imports the seed episodes.

Safe to run on every start: existing users are left alone and the episode
import skips everything that is already there.

    python -m app.seed
"""
import json
import logging
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.importer import import_episodes
from app.logging_setup import setup_logging
from app.models import User
from app.security import hash_password

SEED_DIR = os.getenv("SEED_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "seed"))
log = logging.getLogger("app.seed")


def seed_users(db):
    with open(os.path.join(SEED_DIR, "users.json")) as f:
        people = json.load(f)

    created = 0
    for person in people:
        email = person["email"].lower()
        if db.scalar(select(User).where(User.email == email)):
            continue
        db.add(User(email=email, name=person["name"], role=person["role"],
                    organisation=person.get("organisation"),
                    password_hash=hash_password(person["password"])))
        created += 1
    db.commit()
    return created


def main():
    setup_logging()
    with SessionLocal() as db:
        created = seed_users(db)
        with open(os.path.join(SEED_DIR, "episodes.csv"), newline="", encoding="utf-8-sig") as f:
            report = import_episodes(db, f)
    log.info("seed finished", extra={"fields": {
        "users_created": created, "episodes_imported": report["imported"],
        "episodes_skipped": report["skipped"],
    }})


if __name__ == "__main__":
    main()
