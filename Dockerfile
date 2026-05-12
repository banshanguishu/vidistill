FROM python:3.12-slim

# System deps: ffmpeg for audio extraction, WeasyPrint runtime libs, fonts for CJK PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

# Copy source
COPY src ./src
RUN poetry install --only-root

# Create the output directory
RUN mkdir -p /tmp/vidistill

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "vidistill.main:app", "--host", "0.0.0.0", "--port", "8000"]
