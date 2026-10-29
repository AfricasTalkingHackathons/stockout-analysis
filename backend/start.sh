#!/bin/sh
set -e
alembic upgrade head
python -m app.seed reference
if [ "${DEMO_MODE:-true}" = "true" ]; then
  python -m app.seed demo
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
