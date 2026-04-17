import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from ....adapters.base import OutgoingMessage
from ....adapters.telegram import TelegramAdapter
from ....ai.agent import process_user_message
from ....core.database import get_db
from ....services.cart_service import CartService
from ....services.order_service import OrderService
from ....services.payment_service import PaymentService
from ....services.memory_service import MemoryService
from ....services.command_service import CommandService

logger = logging.getLogger(__name__)
router = APIRouter()

# Instantiate Singletons
telegram_adapter = TelegramAdapter()
cart_service = CartService()
order_service = OrderService()
payment_service = PaymentService()
memory_service = MemoryService()
command_service = CommandService(cart_service)


class IncomingChatMessage(BaseModel):
    platform: str
    user_id: str
    text: str
    username: str | None = None
    display_name: str | None = None

@router.post("/chat/process_message")
async def process_message_endpoint(
    payload: IncomingChatMessage,
    db: AsyncSession = Depends(get_db)
):
    """
    Internal API endpoint designed to receive messages from external bot polling scripts.
    It synchronously waits for the LLM response and returns the string back.
    """
    if not payload.text:
        return {"status": "skipped", "reason": "No text"}

    # 1. Ensure user exists
    user = await order_service.get_or_create_user(
        db, payload.platform, payload.user_id, payload.username, payload.display_name
    )

    # Intercept Commands (Slash commands or Owner Buttons) before hitting AI Agent
    cmd_result = await command_service.execute(payload.text, payload.platform, payload.user_id)
    if cmd_result is not None:
        reply_text, buttons = cmd_result
        
        # Fresh start logic
        if payload.text.startswith("/start"):
            await memory_service.clear_history(payload.platform, payload.user_id)
            await cart_service.clear_cart(payload.platform, payload.user_id)
            
        return {
            "status": "ok",
            "response_text": reply_text,
            "buttons": buttons
        }

    # 2. Get short term memory
    chat_history = await memory_service.get_history(payload.platform, payload.user_id)

    # 3. Process AI
    try:
        reply_text, full_history, buttons = await process_user_message(
            payload.platform, payload.user_id, payload.text, chat_history
        )
        await memory_service.save_history(payload.platform, payload.user_id, full_history)
    except Exception as e:
        logger.error(f"AI processing error: {e}")
        reply_text = "Xin lỗi con, hiện tại cô đang bận xíu, chờ xíu nha."
        buttons = []

    return {
        "status": "ok",
        "response_text": reply_text,
        "buttons": buttons
    }


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
            
            # 6. Persist everything
            await db.commit()

    return {"status": "ok"}
