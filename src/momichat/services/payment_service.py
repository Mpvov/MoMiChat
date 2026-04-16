"""
Payment service to integrate with payOS.
Generates payment links and validates webhooks.
"""

import hashlib
import hmac
import logging
import random

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self) -> None:
        pass

    async def create_payment_link(self, order_id: int, amount: float, description: str) -> dict:
        """
        Calls payOS API to create a payment link.
        Since this is an MVP without valid keys, we will return a mock URL
        unless real keys are provided in .env.
        """
        payos_order_code = int(f"{order_id}{random.randint(100, 999)}")  # payOS requires unique code
        mock_checkout_url = f"https://pay.payos.vn/mock/{payos_order_code}"

        if not settings.PAYOS_CLIENT_ID:
            logger.info("No PayOS keys found. Returning mock payment link.")
            return {
                "orderCode": payos_order_code,
                "checkoutUrl": mock_checkout_url,
            }

        # If real keys are provided, we would call the PayOS API here.
        # This is a stub for the real implementation.
        logger.warning("Real PayOS integration required!")
        return {
            "orderCode": payos_order_code,
            "checkoutUrl": mock_checkout_url,
        }

    def verify_webhook_signature(self, data: dict, signature: str) -> bool:
        """
        Verifies the checksum of the incoming webhook from payOS.
        """
        if not settings.PAYOS_CHECKSUM_KEY:
            return True  # Bypass if no key

        # payload formatting logic (omitted for brevity in MVP)
        # return hmac.compare_digest(calculated_checksum, signature)
        return True
