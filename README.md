# Telegram Bot для учёта продаж

Бот автоматизирует учёт продаж, броней и предзаказов в Telegram-группах. Включает веб-админку на FastAPI.

## 🚀 Быстрый старт

### Локальный запуск через Docker Compose
```bash
git clone https://github.com/yourusername/telegram-bot.git
cd telegram-bot
cp .env.example .env
# отредактируйте .env
docker-compose up -d
