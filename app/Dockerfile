FROM python:3.12-slim

ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown

ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      dumb-init curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:5000/health || exit 1

ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python -c 'import app; app.init_db()' && gunicorn --bind 0.0.0.0:5000 --workers 2 --graceful-timeout 30 app:app"]
