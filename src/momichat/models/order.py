"""
Order and OrderItem models.
Tracks the full lifecycle: PENDING -> PAID -> PREPARING -> DONE / CANCELED.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class OrderStatus(str, enum.Enum):
    PENDING = "pending"        # Cart submitted, awaiting payment
    PAID = "paid"              # Payment confirmed via payOS webhook
    PREPARING = "preparing"    # Mom started making the order
    DONE = "done"              # Order completed and delivered
    CANCELED = "canceled"      # Unpaid timeout or user-canceled


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False
    )
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # payOS fields
    payos_order_code: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    payos_checkout_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="orders")  # noqa: F821
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Order {self.id} status={self.status}>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(String(20), nullable=False)   # e.g. "TS01"
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[str] = mapped_column(String(1), default="M")          # "M" or "L"
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    toppings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of topping IDs

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items")

    def __repr__(self) -> str:
        return f"<OrderItem {self.item_name} x{self.quantity} ({self.size})>"
