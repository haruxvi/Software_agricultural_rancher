import re

_CONTROL_CHARS = re.compile(r"[\r\n\t\x00-\x1f]")


def sanitize_for_log(value: object, max_length: int = 100) -> str:
    """Sanitiza valores para inclusión segura en logs. Elimina control chars y trunca."""
    s = str(value)[:max_length]
    return _CONTROL_CHARS.sub("_", s)
