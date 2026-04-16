# ============================================================
# Axelo JSReverse — Multi-stage Dockerfile
# Stage 1: Build TypeScript/Vite frontend
# Stage 2: Python 3.12 runtime + Playwright Chromium
# ============================================================

# ── Stage 1: Frontend Build ───────────────────────────────────
FROM node:18-slim AS frontend-builder

WORKDIR /app/axelo/web/ui

# Cache npm install layer separately
COPY axelo/web/ui/package*.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY axelo/web/ui/ ./
RUN npm run build


# ── Stage 2: Python Runtime ───────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Minimal system utilities only (Playwright --with-deps handles browser libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python project metadata first for dependency caching
COPY pyproject.toml ./
COPY axelo/ ./axelo/

# Install Python dependencies (core + platform extras)
RUN pip install --no-cache-dir -e ".[platform]"

# Install Playwright Chromium — let --with-deps resolve all system libs
# This avoids hard-coding apt package names that change between Debian releases
RUN playwright install --with-deps chromium

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/axelo/web/ui/dist ./axelo/web/ui/dist

# Create workspace mount point (Railway Volume mounts here)
RUN mkdir -p /app/workspace

# ── Environment defaults (override via Railway Variables) ─────
ENV AXELO_WORKSPACE=/app/workspace
ENV AXELO_HEADLESS=true
ENV AXELO_BROWSER=chromium
# Unset channel so Playwright uses its bundled Chromium
ENV AXELO_BROWSER_CHANNEL=
ENV AXELO_MODEL=deepseek-v3
ENV AXELO_LOG_LEVEL=info
ENV AXELO_PLATFORM_ENVIRONMENT=prod

EXPOSE 7788

# Health check — uses $PORT (Railway) or falls back to 7788
HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-7788}/ || exit 1

# Use shell form so ${PORT:-7788} is expanded at runtime
CMD axelo web --port ${PORT:-7788} --no-open
