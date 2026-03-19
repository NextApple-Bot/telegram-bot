import re

def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы MarkdownV2.
    Поддерживает: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def escape_markdown_v1(text: str) -> str:
    """
    Экранирует для стандартного Markdown (не V2).
    Поддерживает: _ * ` [
    """
    escape_chars = r'_*`['
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)
