# ITBIS backend — FastAPI application image.
#
# Built from the repository root so it can also copy ml_model/, e.g.:
#   docker build -f backend/Dockerfile -t itbis-backend .
# docker-compose.yml does this for you.
#
# Python 3.12 matches the dev virtualenv the shipped model artifacts were
# pickled with (scikit-learn 1.7.2, see backend/requirements.txt) — a
# different Python/sklearn build can fail to unpickle them.
FROM python:3.12-slim AS base

# libpq5 is needed at runtime for asyncpg's C extension; build-essential and
# libpq-dev only for compiling wheels, so they are removed after install to
# keep the image slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && pip install --no-cache-dir -r /app/backend/requirements.txt \
    && apt-get purge -y --auto-remove build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend /app/backend
# The model artifacts model_service.py resolves by default
# (backend/app/modules/anomaly/application/model_service.py, _PROJECT_ROOT):
# five parents up from that file, i.e. the repo root. ITBIS_MODEL_PATH
# below is set explicitly so this doesn't depend on that path arithmetic.
COPY ml_model /app/ml_model

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ITBIS_MODEL_PATH=/app/ml_model/itbis_behavior_model_v3.joblib

WORKDIR /app/backend

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
