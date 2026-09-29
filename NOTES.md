# Notes

## 1. Design

### Data model

```
users ─────────────┐
  id, email,       │ client_id
  role, is_active  ▼
             dataset_requests ──────────────┐
               id, task_name,               │ request_id
               episodes_requested,          ▼
               deadline, status      status_changes   (append-only history)
                     ▲                 from_status, to_status,
                     │ request_id      changed_by_id, changed_at, comment
                     │
               assignments
                 episode_id UNIQUE ──► episodes
                                         episode_id (PK, from the recording system),
                                         robot_id, task_name, recorded_at,
                                         duration_seconds, operator_name, quality
```

**Where state lives.** Everything lives in PostgreSQL. `dataset_requests.status` holds the current status; `status_changes` holds how it got there. The API keeps no state between requests; the login token only carries the user id, and the user is loaded from the database on every call.

**Rules and where each one is enforced:**

| Rule | Enforced by |
|---|---|
| An episode is on at most one request | `UNIQUE (assignments.episode_id)` in the database, plus a friendly check in the API |
| Valid statuses, positive counts and durations, valid quality and role | `CHECK` constraints in the migration |
| Who may make which status move | the `TRANSITIONS` table in `workflow.py`, the only place this rule lives |
| Enough episodes before `delivered` | `workflow.change_status`, with a row lock on the request |
| Only good/usable can be assigned; only while `in_progress` | `routers/requests.py` |
| Re-import never duplicates | the source `episode_id` is the primary key, and inserts use `ON CONFLICT DO NOTHING` |

### The three hardest decisions

**1. What a re-import should do with an episode that already exists but has different values.** Overwriting looks convenient, but an episode may already be delivered to a client, and silently changing its quality after acceptance would be wrong. So the import never updates: an identical row is reported as `already_imported`, and a different row is reported as `conflicts_with_existing` and left alone. The same rule applies within one file: when an id appears twice with different data (EP-00011 is both `bad` and `good` in the seed file), I keep the first row and report the second, instead of guessing which is right. Corrections would need an explicit "update episode" action with its own audit trail.

**2. How to stop two operators assigning the same episode at the same moment.** A check in Python ("is it already assigned?") has a race: two requests can both pass the check and both insert. The real guarantee is the `UNIQUE` constraint on `assignments.episode_id`. If the race happens, the second insert fails with an integrity error and the API returns 409. There is a test that inserts directly and proves the database blocks it. Status changes and assignments also lock the request row (`SELECT ... FOR UPDATE`), so an operator cannot remove an episode while someone else marks the same request as delivered.

**3. Dates in the export.** The file mixes `2026-08-14T09:20:00`, `2026-08-14 09:12:00`, `...Z` and `14/08/2026 09:15`, and none of them carry a timezone. I accept all four, read slashes as day/month (the local convention; `14/08` cannot be month-first anyway), and treat every time as UTC. Analytics days are UTC days. If the recording system actually writes Kigali local time, times would be two hours off; that is a one-line change in `importer.parse_date`, and it is the first thing I would ask the recording team.

### Import rules

| Problem in the row | Decision |
|---|---|
| Spaces and casing (`  Pick Cup `, `Good`, `USABLE`, `ep-00003`, ` arm-01`) | normalised and imported |
| Missing operator name | imported with a warning (informational field, no rule depends on it) |
| Missing/invalid id, missing/unknown robot, missing task | skipped |
| Unreadable date | skipped |
| Duration not a whole number from 1 to 3600 (blank, `N/A`, `-5`, `45.5`, `999999`) | skipped; episodes are short clips, so over an hour is treated as a bad value |
| Quality not good/usable/bad (blank, `excellent`) | skipped; guessing quality would affect what can be delivered |
| Wrong number of columns | skipped as `malformed_row` |
| Blank lines | counted as `blank_line`, not treated as data |

Every skipped row is reported with its line number and reason. For the seed file: 189 rows read, 173 imported, 16 skipped; a second run imports 0.

### Other decisions the brief left open

- Only clients create requests; staff cannot accept or reject on a client's behalf.
- Episodes can be assigned or removed only while a request is `in_progress`. A rejected request goes back to `in_progress`, where the operator can swap episodes.
- More episodes than requested may be assigned (a buffer can be useful); fewer blocks delivery.
- A request's `task_name` is free text from the client, so it is not forced to match episode task names. The episode picker starts filtered on the request's task when it matches one.
- A client asking for another client's request gets 404, not 403, so they cannot learn it exists.
- Analytics: "time from submitted to delivered" runs from request creation to its *first* delivery. Request figures cover requests created within the date range.

## 2. What I left out, and the next two days

Left out or simplified on purpose:
- No stretch item. I used the time for tests, measuring at volume, and these notes.
- No UI for user management; admins use the API (`/docs` makes this easy).
- Tokens cannot be revoked before they expire, except by deactivating the user. There is no refresh token and no login rate limiting.
- Known robots are a constant in the code, not a table.
- Import runs are not stored; the report is returned once and a summary is logged.
- The request list is not paginated (fine for hundreds of requests, not for tens of thousands).
- No browser end-to-end tests in CI. I tested the full flow by hand in a browser.

With two more days:
1. Store each import run (who, when, file name, report) so skipped rows can be reviewed later.
2. Add login rate limiting and shorter tokens with refresh.
3. Add a robots table and an admin page for users.
4. Add a daily rollup table for analytics (see section 5).
5. Add one Playwright end-to-end test in CI for the client-to-operator flow.
6. Do the real-time stretch item (SSE) so operators see new requests without refreshing.

## 3. Something that went wrong

**The first migration run crashed with `ModuleNotFoundError: No module named 'app'`.** The error was raised from `migrations/env.py` on its import of `app.config`. The code was fine; the question was where Python looks for modules. Running `python -c "import app"` from `backend/` worked, so the package itself was importable. The difference was that the `alembic` command does not add the current directory to `sys.path` the way `python -m` does. Adding `prepend_sys_path = .` to `alembic.ini` fixed it.

**A test gap I found by breaking the code on purpose.** After the suite passed, I changed the workflow so clients were allowed to mark requests as delivered, expecting a test to fail. None did: my test only checked that clients could not *start* a request. I rewrote it to try every operator-owned step as a client (`in_progress`, `delivered`, and `rejected → in_progress`), and that mutation now fails the suite. I did the same with the quality rule (allowing `bad` episodes), which the existing tests did catch.

**Slow tests.** The first full run took 94 seconds. Every test logs in, and bcrypt is deliberately slow. I made the bcrypt cost configurable and set it low only for tests; production keeps 12 rounds. The suite now runs in about 4 seconds.

## 4. Security

**Passwords.** bcrypt with 12 rounds and a random salt per password. Login returns the same message for a wrong email, a wrong password, and a deactivated account. It also checks against a dummy hash when the email does not exist, so response time does not reveal which emails are registered.

**Tokens.** Signed JWT (HS256) holding only the user id, expiring after 8 hours. The signing secret comes from the environment (`JWT_SECRET`), never from the code in production. The user is loaded from the database on every request, so deactivating a user or changing their role takes effect immediately, even for tokens already issued. In the browser the token is kept in `sessionStorage`, so it is gone when the tab closes.

**Input validation.** Pydantic validates every request body (lengths, ranges, email format, allowed roles, deadline not in the past). All SQL uses bound parameters, including the hand-written analytics queries. CSV uploads are limited to 50 MB, must be UTF-8, and must have the exact expected header. The database has its own `CHECK` and `UNIQUE` constraints as a second line of defence.

**The two vulnerabilities I would worry about most:**

1. **Broken object-level authorization**, where a client reads or changes another client's request by changing the id in the URL. This is the most common serious bug in systems like this one. Every request lookup goes through one function (`load_request`), which applies the ownership rule, and there are tests for reading, listing, viewing assignments and accepting across clients. The risk is a future endpoint that queries requests directly and skips that function. I would add a review checklist item, and eventually a test that calls every request route as the wrong client.
2. **Stolen tokens.** A token works for up to 8 hours and cannot be individually revoked. Stored in `sessionStorage`, it can be read by any script on the page, so a cross-site scripting bug would expose it. React escapes output by default, and the UI renders no raw HTML. In production I would move to short-lived tokens with a refresh token in an `HttpOnly` cookie, add a Content-Security-Policy header, and add rate limiting on `/auth/login` against password guessing.

## 5. Scale

**Measured.** With 1,000,173 episodes on a laptop-class machine:

| Operation | Time |
|---|---|
| Import 1M rows (CLI) | 203 s, about 5,000 rows/s |
| Re-import the same 1M rows | 43 s, 0 imported |
| Per-day, per-robot count for one month | 62 ms (uses the `recorded_at` index) |
| Same for a full year | 271 ms (parallel full scan) |
| Top 5 tasks by good episodes, full year | 212 ms |
| Whole `/analytics` endpoint, full year | about 0.7 s |
| Filtered episode list (`/episodes`) | about 0.13 s |

**5 million episodes.** Every analytics number is a `GROUP BY` inside PostgreSQL, and no episode rows are loaded into Python. The index on `recorded_at` keeps short date ranges fast regardless of table size. Wide ranges read most of the table, so they grow roughly linearly: expect 1 to 1.5 s for a full year at 5M rows. That is acceptable for an internal dashboard. Beyond that, the fix is a small `episode_daily_stats` table (day, robot, task, quality, count), updated during import. All three analytics queries would then read a few thousand rows instead of millions.

**What breaks first at 10× users.**
- The API runs as one process with a default connection pool of 5 (+10 overflow). Under load, requests queue for a connection before PostgreSQL is anywhere near busy. The fix: run several workers and put PgBouncer in front of the database.
- Login is CPU-heavy because of bcrypt, so a burst of logins slows everything else. More workers help, and so does rate limiting.
- `GET /requests` returns all rows. It needs pagination.

**What breaks first at 100× episodes.**
- **Import.** At 5,000 rows/s, a 20M-row file takes over an hour inside one HTTP-sized operation, and the whole file is held in memory. I would stream the file into a staging table with PostgreSQL `COPY`, clean and deduplicate it there with SQL, and move new rows across with one `INSERT ... SELECT ... ON CONFLICT DO NOTHING`. It would run as a background job with progress reporting, instead of inside the request.
- **The episode list's `count(*)` for the total.** It gets slower as the table grows. I would switch to keyset pagination (continue after the last `recorded_at` and id) and show an estimated total.
- **Analytics over very wide ranges.** The rollup table above fixes this. Monthly partitioning of `episodes` on `recorded_at` would also let old months be skipped entirely.

## 6. AI tooling

I used Claude (Anthropic) for some parts. It proposed the design,and helped me test my codes. I ran everything, read every file, and checked the behaviour myself: the test suite, the import against the seed file and a 1M-row file, the Docker start-up sequence, and the full UI flow in a browser. I am responsible for the decisions above and can explain or change any part of the code.
