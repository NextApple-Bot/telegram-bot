from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SellerStates(StatesGroup):
    """FSM states for seller module."""
    waiting_for_name = State()
    waiting_for_phone = State()
    confirming = State()
