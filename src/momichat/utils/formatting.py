def escape_markdown(text: str) -> str:
    """
    Escapes characters for Telegram's legacy Markdown (ParseMode.MARKDOWN).
    Reserved characters: *, _, `
    """
    if not text:
        return ""
    # Characters that are reserved in legacy Markdown
    reserved = ['*', '_', '`']
    for char in reserved:
        text = text.replace(char, f"\\{char}")
    return text

def format_italic(text: str) -> str:
    """Safely wraps text in italics if non-empty."""
    if not text or not text.strip():
        return ""
    # Escape existing underscores to prevent breaking the wrapping underscores
    safe_text = escape_markdown(text)
    return f"_{safe_text}_"

def format_bold(text: str) -> str:
    """Safely wraps text in bold if non-empty."""
    if not text or not text.strip():
        return ""
    safe_text = escape_markdown(text)
    return f"*{safe_text}*"
