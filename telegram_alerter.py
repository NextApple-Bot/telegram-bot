import asyncio
import os

from aiogram import Bot


async def send_alert(message: str):
    """Отправляет критическое сообщение админам в Telegram."""
    bot_token = os.getenv("BOT_TOKEN")
    admin_ids_str = os.getenv("ADMIN_ID", "")
    if not bot_token or not admin_ids_str:
        print("❌ Не могу отправить алерт: нет токена или админов")
        return

    admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    bot = Bot(token=bot_token)

    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=f"🚨 {message}")
        except Exception as e:
            print(f"❌ Ошибка отправки алерта админу {admin_id}: {e}")

    await bot.session.close()


if __name__ == "__main__":
    # Пример использования
    asyncio.run(send_alert("Тестовый алерт из telegram_alerter.py"))
