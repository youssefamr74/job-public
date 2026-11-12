FROM node:20-slim AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build


FROM python:3.13-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY backend/requirements.txt .
RUN pip install -r requirements.txt


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/app/data \
    WEB_DIST_DIR=/app/web/dist

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/backend /app/data /app/web \
    && chown -R app:app /app

COPY --from=build /opt/venv /opt/venv
WORKDIR /app/backend
COPY --chown=app:app backend/ .
COPY --from=web --chown=app:app /web/dist /app/web/dist
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

ENTRYPOINT ["./docker-entrypoint.sh"]
