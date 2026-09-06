# --- этап 1: сборка фронтенда --------------------------------------------------
# Собранная статика попадает в образ готовой: на сервере Node не нужен,
# а демонстрация не зависит от шага сборки в момент запуска.
FROM node:22-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# Vite настроен собирать в ../backend/static — внутри образа это /backend/static.
RUN mkdir -p /backend/static && npm run build

# --- этап 2: приложение --------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/src/ ./src/
COPY backend/config/ ./config/
COPY --from=frontend /backend/static ./static

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "src.api.main"]
