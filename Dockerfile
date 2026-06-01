# --- 前端构建阶段 ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 后端运行阶段 ---
FROM python:3.12-slim-bookworm

# System deps: ffmpeg for audio extraction, WeasyPrint runtime libs, fonts for CJK PDF,
# sqlite3 CLI for ad-hoc feedback/jobs queries via `docker exec`
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    sqlite3 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY src ./src
RUN poetry install --only-root

# 前端构建产物（与 config._default_frontend_dist 的 /app/frontend/dist 对齐）
COPY --from=frontend /fe/dist ./frontend/dist

RUN mkdir -p /tmp/vidistill

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "vidistill.main:app", "--host", "0.0.0.0", "--port", "8000"]
