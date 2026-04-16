import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ....adapters.base import OutgoingMessage
from ....adapters.telegram import TelegramAdapter
from ....ai.agent import process_user_message
from ....core.database import get_db
from ....services.cart_service import CartService
from ....services.order_service import OrderService
from ....services.payment_service import PaymentService

logger = logging.getLogger(__name__)
router = APIRouter()

# Instantiate Singletons
telegram_adapter = TelegramAdapter()
cart_service = CartService()
order_service = OrderService()
payment_service = PaymentService()


async def handle_chat_message(raw_payload: dict, db: AsyncSession):
    """Background task to process a single message using our abstract adapter."""
    incoming = telegram_adapter.parse_incoming(raw_payload)
    if not incoming.text:
        return

    # 1. Ensure user exists
    user = await order_service.get_or_create_user(
        db, incoming.platform, incoming.platform_user_id, incoming.username, incoming.display_name
    )

    # 2. Get short term memory (dummy empty list for MVP, usually from Redis)
    chat_history = [] 

    # 3. Process AI
    try:
        reply_text = await process_user_message(
            incoming.platform, incoming.platform_user_id, incoming.text, chat_history
        )
    except Exception as e:
        logger.error(f"AI processing error: {e}")
        reply_text = "Xin lỗi con, hiện tại chú đang bận xíu, chờ xíu nha (Hệ thống lỗi)."

    # 4. Reply
    outgoing = OutgoingMessage(platform_user_id=incoming.platform_user_id, text=reply_text)
    await telegram_adapter.send_message(outgoing)


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Entrypoint for Telegram webhook payload."""
    payload = await request.json()
    background_tasks.add_task(handle_chat_message, payload, db)
    return {"status": "ok"}


@router.post("/payos")
async def payos_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Entrypoint for PayOS successful payment confirmation."""
    payload = await request.json()
    
    # 1. Verify signature
    if not payment_service.verify_webhook_signature(payload):
        return {"status": "error", "message": "Invalid signature"}

    # 2. Extract Data
    order_code = payload.get("data", {}).get("orderCode")
    if order_code:
        order = await order_service.mark_paid(db, int(order_code))
        if order:
            # 3. Notify Owner
            await telegram_adapter.send_to_owner(
                text=f"🚨 CÓ ĐƠN HÀNG MỚI ĐÃ THANH TOÁN (Order {order.id})\nKhách: {order.user.display_name}",
                buttons=[{"text": "Đang chuẩn bị", "data": f"prepare_{order.id}"}]
            )
            # 4. Clear User Cart
            await cart_service.clear_cart(order.user.platform.value, order.user.platform_user_id)
            
            # 5. Notify customer
            msg = OutgoingMessage(
                platform_user_id=order.user.platform_user_id,
                text="Mẹ đã nhận được tiền của con rồi nha! Đang làm nước cho con nè \U0001F970"
            )
            background_tasks.add_task(telegram_adapter.send_message, msg)

    return {"status": "ok"}
