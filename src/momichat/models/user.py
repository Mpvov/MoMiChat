"""
User model - tracks customers across messaging platforms.
Stores platform-specific IDs + display names for the future DSS/recommendation engine.
"""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Platform(str, enum.Enum):
    TELEGRAM = "telegram"
    ZALO = "zalo"
    MESSENGER = "messenger"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")  # noqa: F821

    def __repr__(self) -> str:
        return f"<User {self.platform}:{self.platform_user_id}>"
