from bot.utils.validators import extract_serials, normalize_serial


class TestExtractSerials:
    def test_single_serial_in_parentheses(self):
        assert extract_serials("iPhone 15 (ABC123)") == ["ABC123"]

    def test_multiple_serials(self):
        text = "iPhone (ABC123) and iPad (DEF456)"
        result = extract_serials(text)
        assert set(result) == {"ABC123", "DEF456"}

    def test_serial_with_hyphen(self):
        assert extract_serials("Galaxy (S24-XYZ)") == ["S24-XYZ"]

    def test_serial_with_number_sign(self):
        assert extract_serials("№12345 (№67890)") == ["№67890"]

    def test_all_numeric_serial_10_digits(self):
        assert extract_serials("Check (1234567890)") == ["1234567890"]

    def test_all_numeric_serial_less_than_10_digits(self):
        assert extract_serials("Check (123456789)") == []

    def test_empty_parentheses(self):
        assert extract_serials("Some () text") == []

    def test_non_string_input(self):
        assert extract_serials(None) == []
        assert extract_serials(123) == []

    def test_serial_with_spaces(self):
        assert extract_serials("( ABC 123 )") == ["ABC 123"]

    def test_case_normalization(self):
        result = extract_serials("(abc123)")
        assert result == ["ABC123"]

    def test_multiple_same_serial(self):
        text = "iPhone (ABC123) and backup (ABC123)"
        result = extract_serials(text)
        assert result == ["ABC123"]

class TestNormalizeSerial:
    def test_removes_spaces(self):
        assert normalize_serial(" AB C 123 ") == "ABC123"

    def test_uppercase(self):
        assert normalize_serial("abc123") == "ABC123"

    def test_empty_string(self):
        assert normalize_serial("") == ""

    def test_none(self):
        assert normalize_serial(None) == ""

    def test_already_normalized(self):
        assert normalize_serial("ABC123") == "ABC123"
