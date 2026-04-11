# Telegram Bot для учёта продаж

Бот для автоматизации учёта продаж, броней и предзаказов в Telegram-группах.

## 🚀 Быстрый старт

### Локальный запуск
```bash
# 1. Клонировать репозиторий
git clone https://github.com/yourusername/telegram-bot.git
cd telegram-bot

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # для Linux/Mac
# venv\Scripts\activate  # для Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить переменные окружения
cp .env.example .env
# Отредактировать .env, указав свои токены

# 5. Запустить бота
python main.py
