"""Test setup.

Tests run against a real PostgreSQL database (a separate one called desk_test),
because the import and analytics use PostgreSQL features. The schema is built
with the same Alembic migrations as production, so migrations are tested too.
"""
import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://desk:desk@localhost:5432/desk_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL  # must happen before importing the app
os.environ["BCRYPT_ROUNDS"] = "4"  # fast hashing in tests only

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Episode, User  # noqa: E402
from app.security import hash_password  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
PASSWORD = "password123"


def create_test_database():
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    create_test_database()
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    command.downgrade(config, "base")  # start from nothing every run
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE assignments, status_changes, dataset_requests, "
                          "episodes, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def api():
    return TestClient(app)


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(role="client", **fields):
        counter["n"] += 1
        user = User(email=f"{role}{counter['n']}@test.com", name=f"{role} {counter['n']}",
                    role=role, password_hash=hash_password(PASSWORD), **fields)
        db.add(user)
        db.commit()
        return user
    return _make


@pytest.fixture
def login(api):
    """login(user) -> headers dict with a valid Bearer token."""
    def _login(user):
        res = api.post("/auth/login", json={"email": user.email, "password": PASSWORD})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}
    return _login


@pytest.fixture
def make_episode(db):
    counter = {"n": 0}

    def _make(quality="good", task_name="pick cup", robot_id="arm-01",
              recorded_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)):
        counter["n"] += 1
        episode = Episode(episode_id=f"EP-{counter['n']:05d}", robot_id=robot_id,
                          task_name=task_name, recorded_at=recorded_at,
                          duration_seconds=30, operator_name="Test", quality=quality)
        db.add(episode)
        db.commit()
        return episode
    return _make


@pytest.fixture
def new_request(api, login):
    """new_request(client_user, count) -> the created request as a dict."""
    def _new(client, count=2):
        res = api.post("/requests", headers=login(client), json={
            "task_name": "pick cup", "episodes_requested": count, "deadline": "2030-01-01"})
        assert res.status_code == 201, res.text
        return res.json()
    return _new


@pytest.fixture
def move(api, login):
    """move(user, request_id, status) -> response"""
    def _move(user, request_id, status, comment=None):
        return api.post(f"/requests/{request_id}/status", headers=login(user),
                        json={"status": status, "comment": comment})
    return _move


@pytest.fixture
def assign(api, login):
    def _assign(user, request_id, *episodes):
        ids = [e if isinstance(e, str) else e.episode_id for e in episodes]
        return api.post(f"/requests/{request_id}/assignments", headers=login(user),
                        json={"episode_ids": ids})
    return _assign
