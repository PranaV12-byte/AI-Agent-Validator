# ── Safebot Backend — Dockerfile ─────────────────────────────────────────────
# Multi-stage build: builder installs deps, final image is lean.
# Uses Python 3.11-slim to keep image size down.

FROM python:3.11-slim AS builder

WORKDIR /build

# System deps required to compile asyncpg, psycopg2-binary, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifest first (layer cache optimisation)
COPY pyproject.toml .

# Install all project dependencies into /install prefix
RUN pip install --no-cache-dir --prefix=/install -e .

# ── Final image ───────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Non-root user for security
RUN useradd -m -r safebot && chown -R safebot:safebot /app
USER safebot

EXPOSE 8000

# Gunicorn with UvicornWorker (see gunicorn.conf.py)
CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
