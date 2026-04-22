# Файл: tests/test_utils/test_parser.py (исправлен тест extract_prepayments)
import pytest
from bot.services.payment_parser import extract_payment_amounts, extract_prepayments


def test_extract_payment_amounts_basic():
    text = "Наличные - 1000, терминал 500"
    payments = extract_payment_amounts(text)
    assert payments['cash'] == 1000.0
    assert payments['terminal'] == 500.0


def test_extract_payment_amounts_multiple_numbers_same_type():
    text = "Наличные - 1000 и еще 200"
    payments = extract_payment_amounts(text)
    # Парсер берёт первое число для наличных
    assert payments['cash'] == 1000.0


def test_extract_prepayments():
    text = "П/О 2000 (нал)"
    payments = extract_prepayments(text)
    # П/О с нал -> наличные
    assert payments['cash'] == 2000.0


def test_ignore_prepay_flag():
    text = "П/О 2000\nНаличные 1000"
    payments = extract_payment_amounts(text, ignore_prepay=True)
    assert payments['cash'] == 1000.0
