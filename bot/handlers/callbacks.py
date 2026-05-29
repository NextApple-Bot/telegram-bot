import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.utils.helpers import send_and_clean
from .base import get_main_menu_keyboard, show_inventory, show_help
from bot.repositories.stats import StatsRepository

router = Router()
logger = logging.getLogger(__name__)


async def _safe_delete_message(callback: CallbackQuery):
    """Безопасно удаляет сообщение, игнорируя ошибки."""
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "menu:inventory")
async def menu_inventory(callback: CallbackQuery):
    await callback.answer()
    await _safe_delete_message(callback)
    await show_inventory(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery):
    await callback.answer()
    await _safe_delete_message(callback)
    await show_help(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "menu:stats")
async def menu_stats(callback: CallbackQuery):
    await callback.answer()
    try:
        stats = await StatsRepository.get_today_stats()
        text = (
            f"📊 Статистика на {stats.get('date', 'сегодня')}\n\n"
            f"Продажи: {stats.get('sales_count', 0)}\n"
            f"Предзаказы: {stats.get('preorders_count', 0)}\n"
            f"Бронирования: {stats.get('bookings_count', 0)}"
        )
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        logger.exception("[CALLBACK] Ошибка при получении статистики")
        await callback.message.edit_text("Ошибка при получении статистики.")


@router.callback_query(F.data == "menu:remains")
async def menu_remains(callback: CallbackQuery):
    await callback.answer()
    await _safe_delete_message(callback)
    await show_inventory(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "menu:export_assortment")
async def menu_export_assortment(callback: CallbackQuery):
    await callback.answer()
    await _safe_delete_message(callback)
    await show_inventory(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "menu:clients_by_month")
async def menu_clients_by_month(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "👥 Клиенты по месяцам\n\n"
        "Эта функция пока в разработке.\n"
        "Можно использовать /export_clients для экспорта всех клиентов.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:clear")
async def menu_clear(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🗑 Очистка ассортимента\n\n"
        "Вы уверены, что хотите полностью удалить все товары и категории?\n\n"
        "Данные о клиентах, продажах и статистике останутся.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, очистить всё", callback_data="reset_assortment:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="menu:cancel")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:cancel")
async def process_cancel(callback: CallbackQuery):
    await callback.answer("Отменено")
    await _safe_delete_message(callback)

    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="Главное меню:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )
