import asyncio
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Add 'src' to Python path so 'momichat' is discoverable
src_path = Path(__file__).resolve().parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from momichat.config import settings
from momichat.core.database import async_session_factory
from momichat.models import Order, OrderStatus, User

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

st.set_page_config(page_title="MoMiChat - Quản lý Cửa Hàng", layout="wide")


async def fetch_orders(status: OrderStatus) -> list[Order]:
    async with async_session_factory() as session:
        stmt = (
            select(Order)
            .where(Order.status == status)
            .options(selectinload(Order.user), selectinload(Order.items))
            .order_by(Order.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def update_order_status(order_id: int, new_status: OrderStatus):
    async with async_session_factory() as session:
        stmt = select(Order).where(Order.id == order_id)
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()
        if order:
            order.status = new_status
            await session.commit()


def main():
    st.title("\U0001F9CB Trang quản lý đơn hàng")
    st.markdown("---")

    # Bật chế độ auto-refresh mỗi 5 giây
    if st_autorefresh is not None:
        st_autorefresh(interval=5000, key="order_dashboard_refresh")
    else:
        st.warning("Vui lòng cài đặt streamlit-autorefresh để nhận cập nhật tự động.")

    # Fetch data
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.subheader("Chờ TT (PENDING)")
        pending_orders = loop.run_until_complete(fetch_orders(OrderStatus.PENDING))
        for o in pending_orders:
            with st.container(border=True):
                st.markdown(f"**Đơn #{o.id}** - {o.total_price:,.0f}đ")
                st.caption(f"Khách: {o.user.display_name}")
                if st.button("Hủy đơn", key=f"cancel_{o.id}"):
                    loop.run_until_complete(update_order_status(o.id, OrderStatus.CANCELED))
                    st.rerun()

    with col2:
        st.subheader("Đã TT (PAID)")
        paid_orders = loop.run_until_complete(fetch_orders(OrderStatus.PAID))
        for o in paid_orders:
            with st.container(border=True):
                st.markdown(f"**Đơn #{o.id}** \U0001F4B0")
                if o.delivery_phone: st.caption(f"📞 {o.delivery_phone}")
                if o.delivery_address: st.caption(f"📍 {o.delivery_address}")
                for item in o.items:
                    st.text(f"- {item.item_name} ({item.size}) x{item.quantity}")
                if o.note:
                    st.info(f"Ghi chú: {o.note}")
                if st.button("Bắt đầu làm", key=f"start_{o.id}", type="primary"):
                    loop.run_until_complete(update_order_status(o.id, OrderStatus.PREPARING))
                    st.rerun()

    with col3:
        st.subheader("Đang Làm (PREPARING)")
        prep_orders = loop.run_until_complete(fetch_orders(OrderStatus.PREPARING))
        for o in prep_orders:
            with st.container(border=True):
                st.markdown(f"**Đơn #{o.id}** \U0001F379")
                if o.delivery_phone: st.caption(f"📞 {o.delivery_phone}")
                if o.delivery_address: st.caption(f"📍 {o.delivery_address}")
                for item in o.items:
                    st.text(f"- {item.item_name} ({item.size}) x{item.quantity}")
                if st.button("Giao hàng (Shipping)", key=f"ship_{o.id}", type="primary"):
                    loop.run_until_complete(update_order_status(o.id, OrderStatus.SHIPPING))
                    st.rerun()

    with col4:
        st.subheader("Đang Giao (SHIPPING)")
        ship_orders = loop.run_until_complete(fetch_orders(OrderStatus.SHIPPING))
        for o in ship_orders:
            with st.container(border=True):
                st.markdown(f"**Đơn #{o.id}** 🚚")
                if o.delivery_phone: st.caption(f"📞 {o.delivery_phone}")
                if o.delivery_address: st.caption(f"📍 {o.delivery_address}")
                for item in o.items:
                    st.text(f"- {item.item_name} ({item.size}) x{item.quantity}")
                if st.button("Khách đã nhận (Done)", key=f"done_{o.id}", type="primary"):
                    loop.run_until_complete(update_order_status(o.id, OrderStatus.DONE))
                    st.rerun()

    with col5:
        st.subheader("Đã Xong / Hủy")
        done_orders = loop.run_until_complete(fetch_orders(OrderStatus.DONE))
        canceled_orders = loop.run_until_complete(fetch_orders(OrderStatus.CANCELED))
        
        for o in done_orders[:5]:  # show last 5
            st.success(f"#{o.id} - Đã giao")
        for o in canceled_orders[:5]:
            st.error(f"#{o.id} - Đã hủy")

if __name__ == "__main__":
    main()
