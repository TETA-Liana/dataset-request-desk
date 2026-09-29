import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import engine
from app.logging_setup import setup_logging
from app.routers import analytics, auth, episodes, requests, users

setup_logging()
log = logging.getLogger("app.http")

app = FastAPI(title="Dataset Request Desk")


@app.middleware("http")
async def log_each_request(request: Request, call_next):
    """One structured log line per request: method, path, status, duration, user id."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception:
        log.exception("unhandled error")
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    finally:
        log.info("request", extra={"fields": {
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            # set by get_current_user() in deps.py; missing for anonymous requests
            "user_id": getattr(request.state, "user_id", None),
        }})


@app.get("/health")
def health():
    """Checks the database too, so 'healthy' means the app can actually do its job."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check: database unreachable")
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return {"status": "ok", "database": "ok"}


for module in (auth, users, requests, episodes, analytics):
    app.include_router(module.router)
