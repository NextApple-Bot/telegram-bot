from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_seller_main_menu() -> InlineKeyboardMarkup:
    """Меню для незарегистрированного продавца"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мой профиль", callback_data="seller_profile")],
        [InlineKeyboardButton(text="Зарегистрироваться", callback_data="seller_register")],
    ])


def get_seller_menu_registered() -> InlineKeyboardMarkup:
    """Меню для зарегистрированного продавца"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мой профиль", callback_data="seller_profile")],
        [InlineKeyboardButton(text="Добавить товар", callback_data="seller_add_item")],
        [InlineKeyboardButton(text="Статистика", callback_data="seller_stats")],
        [InlineKeyboardButton(text="Настройки", callback_data="seller_settings")],
    ])
