from aiogram.fsm.state import State, StatesGroup


class AnketaForm(StatesGroup):
    filling = State()  # общее состояние заполнения; текущий шаг хранится в data["step"]


class AdminForm(StatesGroup):
    filling = State()  # заявка на младшего модератора — тот же принцип, но без фото


class RejectForm(StatesGroup):
    waiting_reason = State()  # админ вводит причину отказа


class FixForm(StatesGroup):
    waiting_comment = State()  # админ вводит комментарий "требуется исправление"
