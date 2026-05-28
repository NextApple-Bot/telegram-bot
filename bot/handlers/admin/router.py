from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.service_commands import (
    delete_category_by_id,
    delete_category_if_empty,
    delete_client_by_id,
    delete_purchase_by_id,
    export_clients_csv,
    export_full_report_csv,
    export_purchases_csv,
    find_empty_categories,
    fix_sales_unique,
    list_categories_text,
    merge_categories,
    merge_categories_action,
    reset_assortment_action,
    set_webhook_manually,
    undo_last_deletion,
)

from bot.utils.helpers import send_and_clean
from bot.utils.markdown import escape_markdown_v1

router = Router(name="admin")
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ==================== Экспорт данных ====================

@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Доступ запрещён")
        return
    try:
        file_path = await export_clients_csv()
        await message.answer_document(
            FSInputFile(file_path, filename="clients.csv"),
            caption="Экспорт клиентов"
        )
    except Exception:
        logger.exception("Error exporting clients")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Ошибка при экспорте")


@router.message(Command("export_purchases"))
async def cmd_export_purchases(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Доступ запрещён")
        return
    try:
        file_path = await export_purchases_csv()
        await message.answer_document(
            FSInputFile(file_path, filename="purchases.csv"),
            caption="Экспорт покупок"
        )
    except Exception:
        logger.exception("Error exporting purchases")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Ошибка при экспорте")


@router.message(Command("export_full_report"))
async def cmd_export_full_report(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Доступ запрещён")
        return
    try:
        file_path = await export_full_report_csv()
        await message.answer_document(
            FSInputFile(file_path, filename="full_report.csv"),
            caption="Полный отчёт"
        )
    except Exception:
        logger.exception("Error exporting full report")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Ошибка при экспорте")


@router.message(Command("reset_assortment"))
async def cmd_reset_assortment(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Доступ запрещён")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, удалить всё", callback_data="reset_assortment:confirm")],
        [InlineKeyboardButton(text="Отмена", callback_data="menu:cancel")]
    ])
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text=(
            "⚠️ <b>Внимание!</b>\n\n"
            "Эта команда <b>полностью удалит</b> все товары и категории из ассортимента.\n\n"
            "Данные о клиентах, продажах и статистике останутся нетронутыми."
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )
