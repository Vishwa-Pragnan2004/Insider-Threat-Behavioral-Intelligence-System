#!/bin/sh
# Applies migrations, then runs whatever CMD the image was started with
# (uvicorn in production; docker-compose.yml overrides this for a shell
# during debugging). Mirrors start-backend.ps1's local-dev sequence.
set -e

echo "Applying database migrations..."
python -m alembic upgrade head

exec "$@"
