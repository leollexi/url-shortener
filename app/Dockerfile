# ============================================================
# Production-ready Dockerfile для URL Shortener
# ============================================================
FROM python:3.12-slim

# --- Build-args: версия проставляется при сборке (CI передаёт их) ---
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
# Пробрасываем в ENV, чтобы приложение видело их в рантайме (/version)
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    PYTHONUNBUFFERED=1

WORKDIR /app

# dumb-init - корректно пробрасывает сигналы (SIGTERM) в приложение = graceful shutdown.
# curl - для HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
      dumb-init curl \
    && rm -rf /var/lib/apt/lists/*

# Зависимости отдельно (кэш слоёв)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY app.py .

# --- Безопасность: создаём непривилегированного пользователя и работаем под ним ---
# Раньше контейнер работал под root. Если приложение взломают - злоумышленник
# получит root внутри контейнера. Под обычным пользователем ущерб ограничен.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# HEALTHCHECK: Docker сам будет проверять здоровье контейнера.
# Обращается к /health (который теперь проверяет и БД).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:5000/health || exit 1

# dumb-init как PID 1 -> корректно передаёт SIGTERM gunicorn -> graceful shutdown.
# gunicorn с --graceful-timeout даёт воркерам время доработать текущие запросы.
ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python -c 'import app; app.init_db()' && gunicorn --bind 0.0.0.0:5000 --workers 2 --graceful-timeout 30 app:app"]
