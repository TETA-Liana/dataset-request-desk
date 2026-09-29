#!/bin/sh
# Container start: bring the schema up to date, create seed data, start the API.
# Each step is safe to repeat, so restarting the container is always fine.
set -e

echo "Running migrations..."
alembic upgrade head

echo "Seeding users and episodes..."
python -m app.seed

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
