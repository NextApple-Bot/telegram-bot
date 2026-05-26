from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.seller.menu import get_seller_main_menu, get_seller_menu_registered
from bot.handlers.seller.registration import (
    cancel_seller_registration,
    confirm_seller_registration,
    process_seller_name,
    process_seller_phone,
)
from bot.handlers.seller.states import SellerStates
from bot.repositories.seller_repository import SellerRepository

router = Router(name="seller")


async def _get_seller_welcome_text(username: str | None) -> tuple[str, bool]:
    """Возвращает приветствие и флаг, зарегистрирован ли пользователь."""
    if not username:
        return "👤 <b>Меню продавца</b>", False

    seller = await SellerRepository.get_by_telegram_username(username)
    if seller:
        return f"👋 Добро пожаловать, <b>{seller.name}</b>!", True
    return "👤 <b>Меню продавца</b>", False


@router.message(Command("/seller"))
async def cmd_seller_menu(message: Message, state: FSMContext):
    await state.clear()

    username = message.from_user.username
    text, is_registered = await _get_seller_welcome_text(username)

    if is_registered:
        await message.answer(text, reply_markup=get_seller_menu_registered())
    else:
        await message.answer(text, reply_markup=get_seller_main_menu())


@router.callback_query(F.data == "seller_register")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ваше полное имя:")
    await state.set_state(SellerStates.waiting_for_name)
    await callback.answer()


# Регистрация
router.message.register(process_seller_name, SellerStates.waiting_for_name)
router.message.register(process_seller_phone, SellerStates.waiting_for_phone)
router.callback_query.register(confirm_seller_registration, F.data == "seller_confirm_register")
router.callback_query.register(cancel_seller_registration, F.data == "seller_cancel_register")


@router.callback_query(F.data == "seller_profile")
async def show_seller_profile(callback: CallbackQuery):
    username = callback.from_user.username

    if not username:
        await callback.answer("У вас не установлен username в Telegram", show_alert=True)
        return

    seller = await SellerRepository.get_by_telegram_username(username)

    if seller:
        text = (
            f"📋 <b>Ваш профиль</b>\n\n"
            f"👤 Имя: <b>{seller.name}</b>\n"
            f"📱 Телефон: <b>{seller.phone or '—'}</b>\n"
            f"🆔 ID: <code>{seller.id}</code>\n"
            f"📅 Зарегистрирован: {seller.created_at.strftime('%d.%m.%Y')}\n"
            f"✅ Статус: {'Активен' if seller.is_active else 'Неактивен'}"
        )
        menu = get_seller_menu_registered()
    else:
        text = (
            "📋 <b>Профиль</b>\n\n"
            "Вы ещё не зарегистрированы как продавец.\n"
            "Нажмите кнопку \"Зарегистрироваться\" в меню."
        )
        menu = get_seller_main_menu()

    await callback.message.edit_text(text, reply_markup=menu)
    await callback.answer()
