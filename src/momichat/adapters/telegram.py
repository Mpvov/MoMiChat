"""
Telegram adapter - concrete implementation of MessagingAdapter.
Handles parsing Telegram webhook updates and sending replies via Bot API.
"""

import logging

import httpx

from ..config import settings
from .base import IncomingMessage, MessagingAdapter, OutgoingMessage

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


class TelegramAdapter(MessagingAdapter):
    """Concrete adapter for Telegram Bot API."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=10.0)

    def parse_incoming(self, raw_data: dict) -> IncomingMessage:
        """Parse a Telegram Update object into our normalized format."""
        message = raw_data.get("message", {})
        from_user = message.get("from", {})

        return IncomingMessage(
            platform="telegram",
            platform_user_id=str(from_user.get("id", "")),
            username=from_user.get("username"),
            display_name=(
                f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()
                or None
            ),
            text=message.get("text", ""),
            raw_payload=raw_data,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        """Send a text message (and optionally a photo for QR) to a Telegram user."""
        # Send QR image if present
        if message.image_url:
            await self.client.post(
                f"{TELEGRAM_API}/sendPhoto",
                json={
                    "chat_id": message.platform_user_id,
                    "photo": message.image_url,
                    "caption": message.text,
                    "parse_mode": "Markdown",
                },
            )
        else:
            payload: dict = {
                "chat_id": message.platform_user_id,
                "text": message.text,
                "parse_mode": "Markdown",
            }
            # Attach inline keyboard buttons if provided
            if message.buttons:
                payload["reply_markup"] = {
                    "inline_keyboard": [
                    [{"text": b["text"], "callback_data": b.get("data") or b.get("callback_data", "")}]
                    for b in message.buttons
                    ]
                }
            await self.client.post(f"{TELEGRAM_API}/sendMessage", json=payload)

    async def send_to_owner(self, text: str, buttons: list[dict] | None = None) -> None:
        """Push a notification to the shop owner's Telegram chat."""
        payload: dict = {
            "chat_id": settings.owner_chat_id_clean,
            "text": text,
            "parse_mode": "Markdown",
        }
        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": b["text"], "callback_data": b.get("data") or b.get("callback_data", "")}]
                    for b in buttons
                ]
            }
        resp = await self.client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        if resp.status_code != 200:
            logger.error(f"Failed to notify owner: {resp.text}")
