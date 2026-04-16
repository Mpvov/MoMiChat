"""
Cart service - Redis-backed shopping cart for active user sessions.
Each user gets a cart keyed by their platform + user ID.
Cart is destroyed after successful payment (post-payment lockout).
"""

import json
import logging

import redis.asyncio as redis

from ..config import settings

logger = logging.getLogger(__name__)

# Redis key prefix
CART_PREFIX = "cart:"
CART_TTL = 60 * 60  # 1 hour expiry for inactive carts


def _cart_key(platform: str, user_id: str) -> str:
    return f"{CART_PREFIX}{platform}:{user_id}"


class CartService:
    """Manages per-user shopping carts stored in Redis."""

    def __init__(self) -> None:
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def get_cart(self, platform: str, user_id: str) -> list[dict]:
        """Retrieve the current cart items for a user."""
        key = _cart_key(platform, user_id)
        data = await self.redis.get(key)
        if data is None:
            return []
        return json.loads(data)

    async def add_item(
        self,
        platform: str,
        user_id: str,
        item_id: str,
        item_name: str,
        size: str,
        quantity: int,
        unit_price: float,
        toppings: list[str] | None = None,
    ) -> list[dict]:
        """Add an item to the user's cart. Returns the updated cart."""
        cart = await self.get_cart(platform, user_id)
        cart.append({
            "item_id": item_id,
            "item_name": item_name,
            "size": size,
            "quantity": quantity,
            "unit_price": unit_price,
            "toppings": toppings or [],
        })
        key = _cart_key(platform, user_id)
        await self.redis.set(key, json.dumps(cart, ensure_ascii=False), ex=CART_TTL)
        return cart

    async def remove_item(self, platform: str, user_id: str, index: int) -> list[dict]:
        """Remove an item from the cart by its index. Returns updated cart."""
        cart = await self.get_cart(platform, user_id)
        if 0 <= index < len(cart):
            cart.pop(index)
        key = _cart_key(platform, user_id)
        await self.redis.set(key, json.dumps(cart, ensure_ascii=False), ex=CART_TTL)
        return cart

    async def get_total(self, platform: str, user_id: str) -> float:
        """Calculate the total price of all items in the cart."""
        cart = await self.get_cart(platform, user_id)
        return sum(item["unit_price"] * item["quantity"] for item in cart)

    async def clear_cart(self, platform: str, user_id: str) -> None:
        """Destroy the cart entirely (called after payment or cancellation)."""
        key = _cart_key(platform, user_id)
        await self.redis.delete(key)

    async def cart_summary(self, platform: str, user_id: str) -> str:
        """Generate a human-readable cart summary string."""
        cart = await self.get_cart(platform, user_id)
        if not cart:
            return "Giỏ hàng trống 🛒"
        lines = []
        total = 0.0
        for i, item in enumerate(cart, 1):
            subtotal = item["unit_price"] * item["quantity"]
            total += subtotal
            topping_str = f" + {', '.join(item['toppings'])}" if item["toppings"] else ""
            lines.append(
                f"{i}. {item['item_name']} (Size {item['size']}){topping_str}"
                f" x{item['quantity']} = {subtotal:,.0f}đ"
            )
        lines.append(f"\n💰 *Tổng: {total:,.0f}đ*")
        return "\n".join(lines)
