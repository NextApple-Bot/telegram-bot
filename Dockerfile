# ---- Базовый образ для зависимостей ----
FROM python:3.11-slim AS builder

# Установка только необходимых системных зависимостей для asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей в отдельную папку
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- Финальный образ ----
FROM python:3.11-slim

# Создание непривилегированного пользователя для безопасности
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

# Установка только runtime-зависимостей (без build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование установленных пакетов из builder
COPY --from=builder --chown=app:app /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

# Копирование кода приложения
COPY --chown=app:app . .

# Переключение на непривилегированного пользователя
USER app

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
