from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from .base import (
    router, logger, UploadStates, AssortmentConfirmState,
    show_inventory, show_help, cancel_action, start_upload_selection,
    get_main_menu_keyboard, process_full_text
)
from .topics import export_assortment_to_topic

# Хранилище ID последних сообщений статистики и финансов для каждого чата
last_stats_message = {}
last_finance_message = {}


@router.callback_query(F.data.startswith("menu:"))
async def process_menu_callback(callback: CallbackQuery, bot, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if action == "inventory":
        await show_inventory(bot, chat_id)
    elif action == "upload":
        await start_upload_selection(callback.message, bot, state, user_id)
    elif action == "stats":
        s = await stats.get_stats()   # <-- await
        text = (
            f"📊 Статистика за {s['date']}:\n"
            f"• Предзаказов: {s['preorders']}\n"
            f"• Броней: {s['bookings']}\n"
            f"• Продаж: {s['sales']}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="reset_stats:confirm")]
        ])

        if chat_id in last_stats_message:
            try:
                await bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=last_stats_message[chat_id],
                    reply_markup=keyboard
                )
            except Exception:
                msg = await callback.message.answer(text, reply_markup=keyboard)
                last_stats_message[chat_id] = msg.message_id
        else:
            msg = await callback.message.answer(text, reply_markup=keyboard)
            last_stats_message[chat_id] = msg.message_id

    elif action == "finance":
        s = await stats.get_stats()   # <-- await
        total = (
            s['sales_terminal'] + s['preorders_terminal'] +
            s['sales_cash'] + s['preorders_cash'] +
            s['sales_qr'] + s['preorders_qr'] +
            s['sales_installment'] + s['preorders_installment'] +
            s['bookings_total']
        )
        text = (
            f"💰 Финансы за {s['date']}:\n"
            f"Терминал: {s['sales_terminal'] + s['preorders_terminal']:.0f} руб.\n"
            f"Наличные: {s['sales_cash'] + s['preorders_cash']:.0f} руб.\n"
            f"QR-код: {s['sales_qr'] + s['preorders_qr']:.0f} руб.\n"
            f"Рассрочка: {s['sales_installment'] + s['preorders_installment']:.0f} руб.\n"
            f"ИТОГО: {total:.0f} руб."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить финансы", callback_data="reset_finances:confirm")]
        ])

        if chat_id in last_finance_message:
            try:
                await bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=last_finance_message[chat_id],
                    reply_markup=keyboard
                )
            except Exception:
                msg = await callback.message.answer(text, reply_markup=keyboard)
                last_finance_message[chat_id] = msg.message_id
        else:
            msg = await callback.message.answer(text, reply_markup=keyboard)
            last_finance_message[chat_id] = msg.message_id

    elif action == "export_assortment":
        await export_assortment_to_topic(bot, user_id)
    elif action == "clear":
        current_state = await state.get_state()
        if current_state is not None:
            await callback.message.answer("⚠️ Сначала завершите текущее действие (/cancel).")
            return
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear:yes"),
             InlineKeyboardButton(text="❌ Нет, отмена", callback_data="confirm_clear:no")]
        ])
        try:
            await callback.message.edit_text(
                "⚠️ Вы уверены, что хотите полностью очистить ассортимент? Это действие необратимо.",
                reply_markup=keyboard
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
    elif action == "cancel":
        await cancel_action(bot, chat_id, state)
        try:
            await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu_keyboard())
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
    elif action == "help":
        await show_help(bot, chat_id)
    else:
        await callback.message.answer("Неизвестная команда")


@router.callback_query(F.data.startswith("confirm_clear:"))
async def process_confirm_clear(callback: CallbackQuery, bot):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    try:
        if action == "yes":
            # Очистка ассортимента
            await inventory.save_inventory([])   # <-- await
            await stats.reset_stats()            # <-- await
            if chat_id in last_stats_message:
                del last_stats_message[chat_id]
            if chat_id in last_finance_message:
                del last_finance_message[chat_id]
            await callback.message.edit_text("✅ Ассортимент полностью очищен. Статистика и финансы сброшены.")
        else:
            await callback.message.edit_text("❌ Очистка отменена.")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())


@router.callback_query(F.data.startswith("reset_stats:"))
async def process_reset_stats(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    if action == "confirm":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_stats:yes"),
             InlineKeyboardButton(text="❌ Нет", callback_data="reset_stats:no")]
        ])
        await callback.message.edit_text("Вы уверены, что хотите обнулить статистику?", reply_markup=keyboard)
    elif action == "yes":
        await stats.reset_stats()   # <-- await
        s = await stats.get_stats() # <-- await
        text = (
            f"📊 Статистика за {s['date']}:\n"
            f"• Предзаказов: {s['preorders']}\n"
            f"• Броней: {s['bookings']}\n"
            f"• Продаж: {s['sales']}"
        )
        await callback.message.edit_text(text)
        last_stats_message[chat_id] = callback.message.message_id
    elif action == "no":
        s = await stats.get_stats() # <-- await
        text = (
            f"📊 Статистика за {s['date']}:\n"
            f"• Предзаказов: {s['preorders']}\n"
            f"• Броней: {s['bookings']}\n"
            f"• Продаж: {s['sales']}"
        )
        await callback.message.edit_text(text)
        last_stats_message[chat_id] = callback.message.message_id


@router.callback_query(F.data.startswith("reset_finances:"))
async def process_reset_finances(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    if action == "confirm":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_finances:yes"),
             InlineKeyboardButton(text="❌ Нет", callback_data="reset_finances:no")]
        ])
        await callback.message.edit_text("Вы уверены, что хотите обнулить финансовые суммы?", reply_markup=keyboard)
    elif action == "yes":
        await stats.reset_finances()   # <-- await
        s = await stats.get_stats()    # <-- await
        total = (
            s['sales_terminal'] + s['preorders_terminal'] +
            s['sales_cash'] + s['preorders_cash'] +
            s['sales_qr'] + s['preorders_qr'] +
            s['sales_installment'] + s['preorders_installment'] +
            s['bookings_total']
        )
        text = (
            f"💰 Финансы за {s['date']}:\n"
            f"Терминал: {s['sales_terminal'] + s['preorders_terminal']:.0f} руб.\n"
            f"Наличные: {s['sales_cash'] + s['preorders_cash']:.0f} руб.\n"
            f"QR-код: {s['sales_qr'] + s['preorders_qr']:.0f} руб.\n"
            f"Рассрочка: {s['sales_installment'] + s['preorders_installment']:.0f} руб.\n"
            f"ИТОГО: {total:.0f} руб."
        )
        await callback.message.edit_text(text)
        last_finance_message[chat_id] = callback.message.message_id
    elif action == "no":
        s = await stats.get_stats()   # <-- await
        total = (
            s['sales_terminal'] + s['preorders_terminal'] +
            s['sales_cash'] + s['preorders_cash'] +
            s['sales_qr'] + s['preorders_qr'] +
            s['sales_installment'] + s['preorders_installment'] +
            s['bookings_total']
        )
        text = (
            f"💰 Финансы за {s['date']}:\n"
            f"Терминал: {s['sales_terminal'] + s['preorders_terminal']:.0f} руб.\n"
            f"Наличные: {s['sales_cash'] + s['preorders_cash']:.0f} руб.\n"
            f"QR-код: {s['sales_qr'] + s['preorders_qr']:.0f} руб.\n"
            f"Рассрочка: {s['sales_installment'] + s['preorders_installment']:.0f} руб.\n"
            f"ИТОГО: {total:.0f} руб."
        )
        await callback.message.edit_text(text)
        last_finance_message[chat_id] = callback.message.message_id


# -------------------------------------------------------------------
# Обработчики для старого способа загрузки (накопление) – без изменений
# -------------------------------------------------------------------
@router.callback_query(UploadStates.waiting_for_mode, F.data.startswith("upload_mode:"))
async def process_mode_selection(callback: CallbackQuery, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    mode = callback.data.split(":")[1]

    await state.update_data(mode=mode, parts=[])
    await state.set_state(UploadStates.waiting_for_inventory)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="done:finish")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
    try:
        await callback.message.edit_text(
            f"Режим: {'🔁 замена' if mode == 'replace' else '➕ добавление'}\n\n"
            "Отправляйте текстовые сообщения с позициями (можно несколько, каждое будет добавлено в буфер).\n"
            "Когда закончите, нажмите кнопку «✅ Готово» или отправьте команду /done.\n"
            "Также можно загрузить готовый текстовый файл .txt (он обработается сразу).\n"
            "Для отмены используйте /cancel или кнопку ниже.",
            reply_markup=keyboard
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise


@router.callback_query(UploadStates.waiting_for_inventory, F.data == "done:finish")
async def process_done_callback(callback: CallbackQuery, bot, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    data = await state.get_data()
    parts = data.get("parts", [])
    mode = data.get("mode")
    if not parts:
        await callback.message.answer("❌ Нет накопленных частей. Отправьте текст или загрузите файл.")
        return
    full_text = "\n".join(parts)
    await process_full_text(callback.message, full_text, mode, state, bot)


@router.callback_query(UploadStates.waiting_for_continue, F.data.startswith("continue:"))
async def process_continue(callback: CallbackQuery, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]

    if action == "add_more":
        await state.update_data(parts=[])
        await state.set_state(UploadStates.waiting_for_inventory)
        try:
            await callback.message.edit_text(
                "Отправляйте новый список позиций (можно несколько сообщений).\n"
                "Когда закончите, нажмите «✅ Готово» или отправьте /done."
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
    else:
        await state.clear()
        await callback.message.edit_text("✅ Загрузка завершена. Ассортимент обновлён.")
        await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
