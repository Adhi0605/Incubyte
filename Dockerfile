# syntax=docker/dockerfile:1
FROM docker.io/library/node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM docker.io/library/python:3.13-slim-bookworm AS python-build
WORKDIR /build
COPY backend/requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

FROM docker.io/library/python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    FRONTEND_DIST=/app/frontend/dist \
    DATABASE_PATH=/data/inventory.db \
    PORT=8000
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown app:app /data
COPY --from=python-build /opt/venv /opt/venv
COPY backend/app/ /app/backend/app/
COPY --from=frontend-build /build/frontend/dist/ /app/frontend/dist/
COPY scripts/backup.py /app/scripts/backup.py
WORKDIR /app/backend
USER app:app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c 'import json, os, urllib.request; r = urllib.request.urlopen("http://127.0.0.1:" + os.environ.get("PORT", "8000") + "/api/health", timeout=3); assert r.status == 200 and json.load(r) == {"status": "ok"}'
CMD ["sh", "-c", "exec uvicorn app.main:production_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1"]
