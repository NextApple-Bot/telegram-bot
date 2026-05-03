# ... существующий код остаётся без изменений, добавляем в конец файла:

from bot.utils.parser import parse_birth_date, parse_client_data


class TestParseBirthDate:
    def test_full_date(self):
        assert parse_birth_date("01.03.1970") == "01.03.1970"

    def test_short_date(self):
        assert parse_birth_date("01.03") == "01.03"

    def test_invalid_date(self):
        assert parse_birth_date("32.13.2020") is None

    def test_no_date(self):
        assert parse_birth_date("Привет мир") is None

class TestParseClientData:
    def test_phone_and_name(self):
        text = "Иван Иванов +79991234567"
        data = parse_client_data(text)
        assert data['full_name'] == "Иван Иванов"
        assert data['main_phone'] == "+79991234567"

    def test_telegram_and_social(self):
        text = "@telegram_username Соцсети: Instagram"
        data = parse_client_data(text)
        assert data['telegram_username'] == "telegram_username"
        assert data['social_network'] == "Instagram"

    def test_birth_date_from_text(self):
        text = "01.03.1970"
        data = parse_client_data(text)
        assert data['birth_date'] == "01.03.1970"

    def test_no_relevant_info(self):
        text = "Какой-то текст без данных"
        data = parse_client_data(text)
        assert data['full_name'] is None
        assert data['phones'] == []
