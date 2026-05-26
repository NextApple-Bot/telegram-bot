from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_seller_main_menu() -> InlineKeyboardMarkup:
    """Главное меню продавца (для незарегистрированных)."""
    keyboard = [
        [
            InlineKeyboardButton(text="📋 Мой профиль", callback_data="seller_profile"),
            InlineKeyboardButton(text="📦 Мои товары", callback_data="seller_products"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="seller_stats"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="seller_settings"),
        ],
        [
            InlineKeyboardButton(text="📝 Зарегистрироваться", callback_data="seller_register"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_seller_menu_registered() -> InlineKeyboardMarkup:
    """Меню для уже зарегистрированного продавца."""
    keyboard = [
        [
            InlineKeyboardButton(text="📋 Мой профиль", callback_data="seller_profile"),
            InlineKeyboardButton(text="📦 Мои товары", callback_data="seller_products"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="seller_stats"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="seller_settings"),
        ],
        [
            InlineKeyboardButton(text="➕ Добавить товар", callback_data="seller_add_item"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
