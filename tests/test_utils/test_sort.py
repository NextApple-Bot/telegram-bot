from bot.utils.sort import (
    detect_sim_type,
    extract_base_name,
    extract_memory,
    extract_watch_size,
    get_full_model_name,
    normalize_model,
    normalize_name,
    sort_assortment_to_categories,
)


class TestNormalizeName:
    def test_extra_spaces(self):
        assert normalize_name("  iPhone   15  ") == "iPhone 15"

    def test_single_word(self):
        assert normalize_name("iPhone") == "iPhone"

    def test_empty_string(self):
        assert normalize_name("") == ""

class TestNormalizeModel:
    def test_removes_space_after_s(self):
        assert normalize_model("iPhone S 25") == "iPhone S25"

    def test_no_change(self):
        assert normalize_model("iPhone 15") == "iPhone 15"

class TestExtractMemory:
    def test_gb(self):
        assert extract_memory("256GB") == "256GB"

    def test_gb_lowercase(self):
        assert extract_memory("256gb") == "256GB"

    def test_tb(self):
        assert extract_memory("1TB") == "1TB"

    def test_no_memory(self):
        assert extract_memory("iPhone 15") is None

class TestExtractWatchSize:
    def test_mm(self):
        assert extract_watch_size("45mm") == 45

    def test_no_size(self):
        assert extract_watch_size("Apple Watch") is None

class TestDetectSimType:
    def test_esim_only(self):
        assert detect_sim_type("(eSIM)") == "eSIM"

    def test_sim_plus_esim(self):
        assert detect_sim_type("SIM+eSIM") == "SIM+eSIM"

    def test_other(self):
        assert detect_sim_type("Просто текст") == "other"

class TestGetFullModelName:
    def test_removes_brackets(self):
        assert get_full_model_name("iPhone 15 (ABC123)") == "iPhone 15"

    def test_keeps_text_outside_brackets(self):
        assert get_full_model_name("iPhone 15, 128GB (ABC)") == "iPhone 15, 128GB"

class TestExtractBaseName:
    def test_removes_brackets_and_commas(self):
        name = extract_base_name("iPhone 15, 128GB (ABC123)")
        assert name == "iPhone 15"  # обрезается по запятой

    def test_no_comma(self):
        name = extract_base_name("iPhone 15 128GB (ABC)")
        assert name == "iPhone 15 128GB"

class TestSortAssortmentToCategories:
    def test_simple_input(self):
        text = """-iPhone:-
iPhone 15 (ABC)
iPhone 14 (DEF)
"""
        categories = sort_assortment_to_categories(text)
        assert len(categories) == 1
        assert categories[0]["header"] == "iPhone:"
        assert len(categories[0]["items"]) == 2

    def test_dashed_header_style(self):
        text = """------------
iPad:
------------
iPad Pro 11 (XYZ)
"""
        categories = sort_assortment_to_categories(text)
        assert len(categories) == 1
        assert categories[0]["header"] == "iPad:"

    def test_no_header_uses_default(self):
        text = """iPhone 15 (ABC)
Samsung S24 (DEF)
"""
        categories = sort_assortment_to_categories(text)
        assert categories[0]["header"] == "Общее:"

    def test_multiple_categories(self):
        text = """-iPhone:-
iPhone 15 (ABC)
-Samsung:-
Galaxy S24 (DEF)
"""
        categories = sort_assortment_to_categories(text)
        assert len(categories) == 2
        assert categories[0]["header"] == "iPhone:"
        assert categories[1]["header"] == "Samsung:"
