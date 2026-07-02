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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist/ ./frontend/dist/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
