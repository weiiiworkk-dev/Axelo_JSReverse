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

# System deps required by Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libgtk-3-0 \
    fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy Python project metadata first for caching
COPY pyproject.toml ./
COPY axelo/ ./axelo/

# Install Python dependencies (core + platform extras)
RUN pip install --no-cache-dir -e ".[platform]"

# Install Playwright + Chromium browser with all system dependencies
RUN playwright install chromium --with-deps

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/axelo/web/ui/dist ./axelo/web/ui/dist

# Create workspace mount point (Railway Volume mounts here)
RUN mkdir -p /app/workspace

# ── Environment defaults (override via Railway Variables) ─────
ENV AXELO_WORKSPACE=/app/workspace
ENV AXELO_HEADLESS=true
ENV AXELO_BROWSER=chromium
# Unset channel so it uses Playwright's bundled Chromium (not system Chrome)
ENV AXELO_BROWSER_CHANNEL=
ENV AXELO_MODEL=deepseek-v3
ENV AXELO_LOG_LEVEL=info
ENV AXELO_PLATFORM_ENVIRONMENT=prod

EXPOSE 7788

# Health check — waits for server to respond on /
HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:7788/ || exit 1

CMD ["axelo", "web", "--port", "7788", "--no-open"]
