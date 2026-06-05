import logging
import re


_TELEGRAM_BOT_URL_RE = re.compile(r"https://api\.telegram\.org/bot[^/\s]+/")
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"\bbot[0-9A-Za-z:_-]+(?=/)")


def redact_log_message(message: str) -> str:
    message = _TELEGRAM_BOT_URL_RE.sub("https://api.telegram.org/bot<redacted>/", message)
    return _TELEGRAM_BOT_TOKEN_RE.sub("bot<redacted>", message)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = redact_log_message(record.getMessage())
        record.msg = message
        record.args = ()
        return True


_SECRET_REDACTION_FILTER = SecretRedactionFilter()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if _SECRET_REDACTION_FILTER not in handler.filters:
            handler.addFilter(_SECRET_REDACTION_FILTER)

    silverpilot_logger = logging.getLogger("silverpilot")
    silverpilot_logger.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not silverpilot_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        handler.addFilter(_SECRET_REDACTION_FILTER)
        silverpilot_logger.addHandler(handler)
