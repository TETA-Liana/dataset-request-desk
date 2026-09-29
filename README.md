# Dataset Request Desk

An internal web platform that replaces the dataset-request spreadsheet. Clients ask for robot episodes, operators fill the requests by assigning episodes, and clients accept or reject the delivery.

- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16
- Frontend: React 18 (Vite), served by nginx
- Tests: pytest against a real PostgreSQL database

Design decisions, trade-offs and what I would do next are in [NOTES.md](NOTES.md).

## Run it

You need Docker (Docker Desktop on Windows/macOS). From a clean clone:

```bash
docker compose up --build
```

This starts PostgreSQL, runs the migrations, creates the seed users, imports `seed/episodes.csv`, and starts the API and the UI. Every start-up step is safe to repeat, so restarting is fine.

| What | URL |
|---|---|
| Web UI | http://localhost:8081 |
| API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

To start again from an empty database: `docker compose down -v`.

For anything other than local use, copy `.env.example` to `.env` and set a real `JWT_SECRET`.

### Seed users

| Email | Password | Role |
|---|---|---|
| admin@example.com | admin123 | admin |
| ops1@example.com | ops123 | operator |
| ops2@example.com | ops123 | operator |
| client-a@example.com | client123 | client (Acme Robotics) |
| client-b@example.com | client123 | client (Beta Labs) |

Passwords are stored as bcrypt hashes, never in plain text.

## Run the tests

```bash
docker compose up -d db
docker compose run --rm api pytest
```

The tests create and use a separate `desk_test` database. They build the schema by running the Alembic migrations (down to empty, then up), so the migrations are tested every run. The suite takes a few seconds.

The tests focus on what the brief cares about most:

| File | What it proves |
|---|---|
| `test_authorization.py` | every endpoint needs a login; each role is limited to its own actions; clients cannot see each other's requests; deactivation and role changes take effect immediately |
| `test_transitions.py` | only valid status moves, only by the right role; history records who and when; cannot deliver before enough episodes are assigned |
| `test_assignments.py` | one request per episode (also enforced by the database); only good/usable; batches are all-or-nothing |
| `test_import.py` | every cleaning rule; duplicates and conflicts; importing the same file twice creates nothing new; existing episodes are never overwritten |
| `test_analytics.py` | per-day counts, top tasks and the median are correct; the date range is respected |

CI (`.github/workflows/ci.yml`) runs the backend tests against PostgreSQL and builds the frontend on every push.

## Importing episodes

From the UI: log in as an operator, open **Import episodes from CSV** under the request list.

From the command line (inside the API container):

```bash
docker compose exec api python -m app.cli import-episodes /seed/episodes.csv
docker compose exec api python -m app.cli import-episodes /seed/episodes.csv --full   # list every skipped row
```

Both return a report: rows read, imported, skipped, a count per skip reason, and for each skipped row its line number, episode id and reason. The cleaning rules are listed in NOTES.md.

To try a large file, copy it into the container and import it. The UI upload is limited to 50 MB, so use the command line for big files:

```bash
python3 seed/generate_episodes.py 200000 > episodes_large.csv
docker compose cp episodes_large.csv api:/tmp/
docker compose exec api python -m app.cli import-episodes /tmp/episodes_large.csv
```

## Running without Docker

You need Python 3.12, Node 22 and a PostgreSQL 16 server with a `desk` user (password `desk`) that can create databases.

```bash
# backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload      # http://localhost:8000
pytest                             # tests

# frontend (second terminal)
cd frontend
npm install
npm run dev                        # http://localhost:5173, forwards /api to port 8000
```

Set `DATABASE_URL` / `TEST_DATABASE_URL` if your database is somewhere else (format: `postgresql+psycopg://user:password@host:5432/dbname`).

## API overview

All endpoints except `/health` and `/auth/login` need `Authorization: Bearer <token>`.

| Method and path | Who | What |
|---|---|---|
| `POST /auth/login` | anyone | returns a token |
| `GET /auth/me` | any user | the logged-in user |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | admin | list, create, change role or deactivate |
| `GET /requests?status=` | any user | clients see only their own |
| `POST /requests` | client | create a request |
| `GET /requests/{id}` | owner or staff | details and full status history |
| `POST /requests/{id}/status` | depends on the step | move the request through its workflow |
| `GET /requests/{id}/assignments` | owner or staff | episodes on the request |
| `POST /requests/{id}/assignments` | staff | assign a batch of episodes |
| `DELETE /requests/{id}/assignments/{episode_id}` | staff | remove one |
| `GET /episodes?task_name=&quality=&robot_id=&unassigned_only=&assignable_only=` | staff | filtered, paginated list |
| `POST /episodes/import` | staff | upload a CSV |
| `GET /analytics?start=YYYY-MM-DD&end=YYYY-MM-DD` | staff | analytics (both dates inclusive, UTC) |
| `GET /health` | anyone | 200 if the API and database are up, 503 otherwise |

"Staff" means operator or admin.

## Project layout

```
backend/
  app/
    main.py            app setup, request logging middleware, /health
    models.py          database tables
    workflow.py        status rules, all in one table
    importer.py        CSV cleaning and idempotent import
    deps.py            login and role checks used by every route
    security.py        password hashing and tokens
    routers/           one file per area of the API
    seed.py, cli.py    seed data and command-line import
  migrations/          Alembic migrations
  tests/
frontend/src/          React UI
seed/                  data provided with the task
```

## Stretch item

I did not pick a stretch item. I spent the time on the tests, measuring the queries at volume, and the notes. I added CI (the optional nice-to-have) instead.
