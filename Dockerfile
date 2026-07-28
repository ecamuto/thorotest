# Stage 1 — build the frontend (transpile JSX, minify, vendor React + fonts)
FROM node:20-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/
RUN npm run build

# Stage 2 — Python runtime
FROM python:3.12-slim
WORKDIR /app

# Install from the lock file — the same pinned set CI tests against, so the
# image is the artifact that was verified rather than a fresh resolve.
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY backend/ ./backend/
COPY alembic.ini ./
COPY migrations/ ./migrations/
# Version + changelog for the About page (GET /api/about)
COPY package.json CHANGELOG.md ./
COPY --from=frontend /app/frontend/dist/ ./frontend/dist/

# Run as an unprivileged user. uploads/ is the only path the app writes to.
RUN useradd --system --create-home --uid 10001 thorotest \
    && mkdir -p /app/uploads \
    && chown -R thorotest:thorotest /app
USER thorotest

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
