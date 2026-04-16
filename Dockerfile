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

# 【缓存优化】先复制依赖声明文件，创建最小空桩后安装依赖。
# 这样代码改动不会使 pip install / playwright install 层失效。
COPY pyproject.toml ./
# 创建最小空桩，让 pip 能解析 pyproject.toml 安装依赖（代码变化时此层仍有缓存）
RUN mkdir -p axelo && touch axelo/__init__.py && \
    pip install --no-cache-dir -e ".[platform]"

# Playwright 浏览器安装（重，单独缓存，代码变化不触发）
# This avoids hard-coding apt package names that change between Debian releases
RUN playwright install --with-deps chromium

# 真正的代码复制放最后（变化频繁的层放最后，上面的重步骤都有缓存）
COPY axelo/ ./axelo/

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

# PORT: Railway reads this ENV to know which port to health-check and proxy.
# Railway will override this value if it injects its own PORT.
# Must be set here so Railway's health check probes the correct port.
ENV PORT=7788

EXPOSE 7788

# Health check for local `docker run` — Railway ignores this directive entirely
# and instead probes the PORT env var. exec form + sh -c 确保变量展开 AND stderr 可见。
HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=3 \
    CMD ["sh", "-c", "curl -sf http://localhost:${PORT:-7788}/ || exit 1"]

# exec form + sh -c：${PORT:-7788} 在容器启动时展开，2>&1 将 stderr 合并到 stdout，
# 确保 Railway 能捕获所有崩溃日志。
CMD ["sh", "-c", "exec axelo web --port ${PORT:-7788} --no-open 2>&1"]
