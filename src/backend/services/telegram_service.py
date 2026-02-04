"""
Telegram notification service.
Sends messages via Telegram Bot API when enabled in settings.
"""
import logging
import httpx

logger = logging.getLogger(__name__)


async def send_telegram_message(message: str):
    """Send a Telegram message if enabled in runtime settings."""
    try:
        from settings.config import get_runtime_settings
        cfg = get_runtime_settings()

        if not cfg.get("enable_telegram", False):
            logger.debug("Telegram notifications disabled")
            return

        token = cfg.get("telegram_bot_token", "")
        user_id = cfg.get("telegram_user_id", "")

        if not token or not user_id:
            logger.warning("Telegram enabled but bot_token or user_id not set")
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": user_id, "text": message, "parse_mode": "HTML"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info("Telegram message sent successfully")
            else:
                logger.warning(f"Telegram API returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
