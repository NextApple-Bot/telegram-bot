import csv
import tempfile
import os
import aiosqlite
from aiogram.types import FSInputFile
from database import DB_PATH

@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message, bot):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Телефон', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM clients ORDER BY id')
            rows = await cursor.fetchall()
            for row in rows:
                writer.writerow([
                    row['id'],
                    row['full_name'],
                    row['phone'],
                    row['telegram_username'],
                    row['social_network'],
                    row['referral_source'],
                    row['created_at']
                ])

        tmp_path = tmp.name

    try:
        await message.answer_document(
            FSInputFile(tmp_path, filename="clients.csv"),
            caption="📁 Экспорт клиентов"
        )
    finally:
        os.unlink(tmp_path)
