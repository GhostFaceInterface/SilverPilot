import asyncio
import logging
from datetime import timedelta
from telegram import Bot
from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger("silverpilot.services.telegram")


async def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
    attempts: int = 3,
    backoff: float = 2.0,
) -> bool:
    """
    Sends a telegram message using the python-telegram-bot library, with robust retry logic.
    Handles RetryAfter errors by waiting the specified duration + 1.0 second.
    Handles other TelegramError and connection errors using exponential backoff.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram configuration missing (bot_token or chat_id is empty). Message skipped.")
        return False

    for attempt in range(1, attempts + 1):
        try:
            bot = Bot(token=bot_token)
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
            )
            logger.info(
                f"Telegram message sent successfully (chat_id={chat_id}, silent={disable_notification}, attempt {attempt}/{attempts})."
            )
            return True
        except RetryAfter as e:
            seconds = e.retry_after.total_seconds() if isinstance(e.retry_after, timedelta) else float(e.retry_after)
            wait_time = seconds + 1.0
            if attempt == attempts:
                logger.error(f"Failed to send Telegram message due to rate limits after {attempts} attempts.")
                break
            logger.warning(
                f"Telegram rate limit hit (RetryAfter). Waiting {wait_time}s before retry (attempt {attempt}/{attempts})..."
            )
            await asyncio.sleep(wait_time)
        except TelegramError as e:
            if attempt == attempts:
                logger.error(
                    "Failed to send Telegram message after %s attempts; error_type=%s.",
                    attempts,
                    type(e).__name__,
                )
                break
            wait_time = backoff * (2 ** (attempt - 1))  # exponential backoff
            logger.warning(
                "Telegram API error; error_type=%s. Retrying in %ss (attempt %s/%s)...",
                type(e).__name__,
                wait_time,
                attempt,
                attempts,
            )
            await asyncio.sleep(wait_time)
        except Exception as e:
            if attempt == attempts:
                logger.error(
                    "Unexpected connection error sending Telegram message after %s attempts; error_type=%s.",
                    attempts,
                    type(e).__name__,
                )
                break
            wait_time = backoff * (2 ** (attempt - 1))  # exponential backoff
            logger.warning(
                "Connection error sending Telegram message; error_type=%s. Retrying in %ss (attempt %s/%s)...",
                type(e).__name__,
                wait_time,
                attempt,
                attempts,
            )
            await asyncio.sleep(wait_time)

    return False
