"""
Payment service to integrate with payOS.
Generates payment links and validates webhooks.
"""

import logging

from payos import AsyncPayOS
from payos.types import CreatePaymentLinkRequest

from ..config import settings

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self) -> None:
        if settings.PAYOS_CLIENT_ID and settings.PAYOS_API_KEY and settings.PAYOS_CHECKSUM_KEY:
            self.payos = AsyncPayOS(
                client_id=settings.PAYOS_CLIENT_ID,
                api_key=settings.PAYOS_API_KEY,
                checksum_key=settings.PAYOS_CHECKSUM_KEY
            )
        else:
            self.payos = None

    async def create_payment_link(self, order_id: int, amount: float, description: str) -> dict:
        """
        Calls payOS API to create a payment link.
        """
        import time
        # Use Unix timestamp + order_id to guarantee absolute uniqueness 
        # and prevent random number collisions, perfectly fitting in the 53-bit integer limit.
        payos_order_code = int(f"{int(time.time())}{order_id}")

        if not self.payos:
            logger.error("PayOS keys are missing from environment.")
            raise ValueError("PayOS integration is not configured properly.")

        try:
            payment_request = CreatePaymentLinkRequest(
                order_code=payos_order_code,
                amount=int(amount),
                description=description[:25],
                cancel_url="https://buy.payos.vn",  # placeholder 
                return_url="https://buy.payos.vn"   
            )

            payment_link = await self.payos.payment_requests.create(payment_request)
            return {
                "orderCode": payos_order_code,
                "checkoutUrl": payment_link.checkout_url,
            }
        except Exception as e:
            logger.error(f"PayOS API Error: {e}")
            raise RuntimeError(f"Failed to create payment link: {e}")

    def verify_webhook_signature(self, payload: dict) -> bool:
        """
        Verifies the checksum of the incoming webhook from payOS.
        """
        if not self.payos:
            return False  # Failing verification if no keys are set

        try:
            self.payos.webhooks.verify(payload)
            return True
        except Exception as e:
            logger.error(f"Webhook verification failed: {e}")
            return False
