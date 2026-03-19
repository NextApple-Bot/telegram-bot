# ---- Базовый образ для зависимостей ----
FROM python:3.11-slim AS builder

# Установка только необходимых системных зависимостей для asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .

# Установка зависимостей в /install
RUN pip install --user --no-cache-dir -r requirements.txt && \
    # Создаём директорию для переноса
    mkdir -p /install && \
    # Копируем установленные пакеты
    cp -r /root/.local/* /install/

# ---- Финальный образ ----
FROM python:3.11-slim

# Создание непривилегированного пользователя
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

# Установка только runtime-зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование установленных пакетов из builder
COPY --from=builder --chown=app:app /install /home/app/.local

# Установка правильных прав и PATH
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/home/app/.local/lib/python3.11/site-packages:$PYTHONPATH \
    PYTHONUNBUFFERED=1

# Копирование кода приложения
COPY --chown=app:app . .

# Переключение на непривилегированного пользователя
USER app

# Проверка, что uvicorn доступен
RUN python -c "import uvicorn; print('✅ Uvicorn импортирован успешно')"

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
