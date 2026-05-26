from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.handlers.seller.states import SellerStates
from bot.repositories.seller_repository import SellerRepository


async def process_seller_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, введите имя текстом.")
        return

    await state.update_data(full_name=message.text.strip())
    await message.answer("Отлично! Теперь введите номер телефона:")
    await state.set_state(SellerStates.waiting_for_phone)


async def process_seller_phone(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, введите номер телефона.")
        return

    await state.update_data(phone=message.text.strip())
    data = await state.get_data()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, зарегистрировать", callback_data="seller_confirm_register"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="seller_cancel_register"),
            ]
        ]
    )

    await message.answer(
        f"Проверьте данные:\n\n"
        f"• Имя: <b>{data.get('full_name')}</b>\n"
        f"• Телефон: <b>{data.get('phone')}</b>\n\n"
        f"Всё верно?",
        reply_markup=keyboard,
    )
    await state.set_state(SellerStates.confirming)


async def confirm_seller_registration(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    full_name = data.get("full_name")
    phone = data.get("phone")

    telegram_username = callback.from_user.username

    # Пытаемся создать продавца
    seller = await SellerRepository.create_seller(
        name=full_name,
        phone=phone,
        telegram_username=telegram_username,
    )

    if seller is None:
        await callback.message.edit_text(
            "⚠️ Продавец с таким именем и телефоном уже существует.",
            reply_markup=None,
        )
        await state.clear()
        await callback.answer()
        return

    # Успешная регистрация
    await callback.message.edit_text(
        f"✅ <b>Регистрация успешно завершена!</b>\n\n"
        f"Добро пожаловать, <b>{full_name}</b>!\n"
        f"Теперь вы зарегистрированы как продавец.",
        reply_markup=get_seller_menu_after_registration(),
    )
    await state.clear()
    await callback.answer()


def get_seller_menu_after_registration() -> InlineKeyboardMarkup:
    """Меню после успешной регистрации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Мой профиль", callback_data="seller_profile"),
                InlineKeyboardButton(text="📦 Мои товары", callback_data="seller_products"),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="seller_stats"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="seller_settings"),
            ],
        ]
    )


async def cancel_seller_registration(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Регистрация отменена.")
    await callback.answer()
