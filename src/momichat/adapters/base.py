"""
Abstract base adapter for all messaging platforms.
Implements the Adapter/Strategy pattern so Telegram, Zalo, Messenger
can be swapped in by simply writing a new concrete class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IncomingMessage:
    """Normalized message from any platform."""
    platform: str
    platform_user_id: str
    username: str | None
    display_name: str | None
    text: str
    raw_payload: dict  # Original platform-specific data


@dataclass
class OutgoingMessage:
    """Normalized outgoing response to any platform."""
    platform_user_id: str
    text: str
    image_url: str | None = None  # For QR codes
    buttons: list[dict] | None = None  # Inline buttons


class MessagingAdapter(ABC):
    """
    Abstract interface that every messaging platform must implement.
    Adding a new platform = creating a new subclass.
    """

    @abstractmethod
    def parse_incoming(self, raw_data: dict) -> IncomingMessage:
        """Parse raw webhook JSON into a normalized IncomingMessage."""
        ...

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> None:
        """Send a response back to the user on the platform."""
        ...

    @abstractmethod
    async def send_to_owner(self, text: str, buttons: list[dict] | None = None) -> None:
        """Send a notification to the shop owner (Mom)."""
        ...
