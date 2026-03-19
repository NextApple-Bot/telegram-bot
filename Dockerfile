FROM python:3.11-slim

# Устанавливаем системные зависимости, включая Rust
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Rust (требуется для компиляции pydantic-core)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
# Убедимся, что pip обновлён, и установим зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Команда для запуска бота
CMD ["python", "main.py"]
