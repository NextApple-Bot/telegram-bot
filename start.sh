#!/bin/sh
set -e

echo "🚀 Starting Telegram Bot..."

# Run migrations
python run_migrations.py || echo "Migrations skipped or already up to date"

# Start the bot
exec python main.py