# ═══════════════════════════════════════════════════════════════════════════
# PRAHARI · one image, both halves.
#
# Stage 1 builds the frontend. Stage 2 runs the API and serves the built
# frontend from the same origin, so a deployment needs one service and one
# URL — which matters when the deployment budget is a state department's.
# ═══════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --omit=dev --no-audit --fund=false || npm install --no-audit --fund=false
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libgomp is onnxruntime's only shared-library need; curl is for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=ui /ui/dist ./frontend/dist

# Never run as root, and never write into the image.
RUN useradd -m -u 10001 prahari \
    && mkdir -p /app/var/uploads \
    && chown -R prahari:prahari /app
USER prahari

ENV STORAGE_LOCAL_DIR=/app/var/uploads
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

WORKDIR /app/backend
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
