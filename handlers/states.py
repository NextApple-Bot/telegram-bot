from aiogram.fsm.state import State, StatesGroup

class AssortmentConfirmState(StatesGroup):
    """Состояние ожидания подтверждения загрузки ассортимента."""
    waiting_for_confirm = State()

class ArrivalConfirmState(StatesGroup):
    """Состояние ожидания подтверждения добавления товаров."""
    waiting_for_confirm = State()
