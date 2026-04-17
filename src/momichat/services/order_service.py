"""
Order service - persists orders and order items to PostgreSQL.
Handles the full lifecycle: create -> pay -> prepare -> done / cancel.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.order import Order, OrderItem, OrderStatus
from ..models.user import Platform, User

logger = logging.getLogger(__name__)


class OrderService:
    """Business logic for orders backed by PostgreSQL."""

    async def get_or_create_user(
        self,
        db: AsyncSession,
        platform: str,
        platform_user_id: str,
        username: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """Find existing user or create a new profile for tracking."""
        stmt = select(User).where(
            User.platform == Platform(platform),
            User.platform_user_id == platform_user_id,
        )
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                platform=Platform(platform),
                platform_user_id=platform_user_id,
                username=username,
                display_name=display_name,
            )
            db.add(user)
            await db.flush()
            logger.info(f"New user created: {user}")
        else:
            # Update display info if changed
            if username and user.username != username:
                user.username = username
            if display_name and user.display_name != display_name:
                user.display_name = display_name

        return user

    async def create_order(
        self,
        db: AsyncSession,
        user_id: int,
        cart_items: list[dict],
        note: str | None = None,
    ) -> Order:
        """Create a PENDING order from the user's cart items."""
        total = sum(item["unit_price"] * item["quantity"] for item in cart_items)

        order = Order(
            user_id=user_id,
            status=OrderStatus.PENDING,
            total_price=total,
            note=note,
        )
        db.add(order)
        await db.flush()  # Get order.id

        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                item_id=item["item_id"],
                item_name=item["item_name"],
                size=item.get("size", "M"),
                quantity=item.get("quantity", 1),
                unit_price=item["unit_price"],
                toppings=json.dumps(item.get("toppings", []), ensure_ascii=False),
            )
            db.add(order_item)

        await db.flush()
        logger.info(f"Order {order.id} created for user {user_id}, total={total}")
        return order

    async def update_status(
        self, db: AsyncSession, order_id: int, new_status: OrderStatus
    ) -> Order | None:
        """Transition an order to a new status."""
        stmt = select(Order).where(Order.id == order_id)
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        if order:
            order.status = new_status
            await db.flush()
            logger.info(f"Order {order_id} -> {new_status}")
        return order

    async def mark_paid(
        self, db: AsyncSession, payos_order_code: int
    ) -> Order | None:
        """Mark an order as paid using the payOS order code."""
        stmt = (
            select(Order)
            .where(Order.payos_order_code == payos_order_code)
            .options(selectinload(Order.user))
        )
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            await db.flush()
            logger.info(f"Order {order.id} marked PAID via payOS code {payos_order_code}")
        return order

    async def get_orders_by_status(
        self, db: AsyncSession, status: OrderStatus
    ) -> list[Order]:
        """Fetch all orders with a given status (for the Streamlit dashboard)."""
        stmt = (
            select(Order)
            .where(Order.status == status)
            .options(selectinload(Order.items), selectinload(Order.user))
            .order_by(Order.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active_orders(self, db: AsyncSession) -> list[Order]:
        """Fetch all non-DONE orders for the Kanban board."""
        stmt = (
            select(Order)
            .where(Order.status != OrderStatus.DONE)
            .options(selectinload(Order.items), selectinload(Order.user))
            .order_by(Order.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
