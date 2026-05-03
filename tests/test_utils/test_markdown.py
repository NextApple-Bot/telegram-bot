from bot.utils.markdown import escape_markdown, escape_markdown_v1

class TestEscapeMarkdown:
    def test_escapes_special_chars(self):
        text = "Hello _world_ *test*"
        escaped = escape_markdown(text)
        assert escaped == "Hello \\_world\\_ \\*test\\*"

    def test_no_special_chars(self):
        assert escape_markdown("Plain text") == "Plain text"

    def test_all_special(self):
        text = "_*[]()~`>#+-=|{}.!"
        escaped = escape_markdown(text)
        for char in text:
            assert "\\" + char in escaped

class TestEscapeMarkdownV1:
    def test_escapes_v1_chars(self):
        text = "Hello _world_ `code` [link]"
        escaped = escape_markdown_v1(text)
        assert escaped == "Hello \\_world\\_ \\`code\\` \\[link]"

    def test_no_v1_chars(self):
        assert escape_markdown_v1("Plain text") == "Plain text"
