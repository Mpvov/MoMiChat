import logging
from string import Template

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ....adapters.base import OutgoingMessage
from ....adapters.telegram import TelegramAdapter
from ....ai.agent import process_user_message
from ....config import settings
from ....core.database import get_db
from ....models.order import Order, OrderStatus
from ....services.cart_service import CartService
from ....services.command_service import CommandService
from ....services.memory_service import MemoryService
from ....services.order_service import OrderService
from ....services.payment_service import PaymentService

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

    # 3. Process AI — pass pre-loaded user data to avoid duplicate DB query
    user_data = {
        "phone": user.phone,
        "address": user.address,
        "db_user_id": user.id,
    }
    try:
        reply_text, full_history, buttons = await process_user_message(
            payload.platform, payload.user_id, payload.text, chat_history,
            user_data=user_data,
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
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "Invalid signature"},
        )

    # 2. Extract Data
    code = payload.get("code")
    order_code = payload.get("data", {}).get("orderCode")
    
    # Only process successful payments ("00" is success in PayOS)
    if code == "00" and order_code:
        order = await order_service.mark_paid(db, int(order_code))
        if order:
            # Re-fetch with items loaded for the notification
            stmt = select(Order).where(Order.id == order.id).options(
                selectinload(Order.items), selectinload(Order.user)
            )
            res = await db.execute(stmt)
            order = res.scalar_one()

            # 3. Notify Owner with full order details
            msg_text = order_service.format_order_details(order, title="🚨 ĐƠN HÀNG MỚI ĐÃ THANH TOÁN")
            await telegram_adapter.send_to_owner(
                text=msg_text,
                buttons=[{"text": "👨‍🍳 Bắt đầu làm", "data": f"prepare_{order.id}"}]
            )
            # 4. Clear User Cart
            await cart_service.clear_cart(order.user.platform.value, order.user.platform_user_id)
            
            # 5. Notify customer
            msg = OutgoingMessage(
                platform_user_id=order.user.platform_user_id,
                text=f"✅ Đơn hàng đã thanh toán thành công! Cảm ơn con nha"
            )
            background_tasks.add_task(telegram_adapter.send_message, msg)
            
            # 6. Persist everything
            await db.commit()

    return {"status": "ok"}


# ─── Pretty HTML page shown after user succeeds on PayOS ─────────────────────

_SUCCESS_HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Thanh toán thành công — Tiệm trà bé lá</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  }
  .card {
    background: #fff;
    border-radius: 20px;
    box-shadow: 0 8px 32px rgba(0,0,0,.08);
    max-width: 420px; width: 90%;
    padding: 48px 32px; text-align: center;
  }
  .icon { font-size: 56px; margin-bottom: 16px; }
  h1 { font-size: 22px; color: #388e3c; margin-bottom: 8px; }
  p  { color: #555; font-size: 15px; line-height: 1.6; margin-bottom: 24px; }
  .order-code { font-family: monospace; font-weight: 700; color: #333; }
  .btn {
    display: inline-block; padding: 12px 28px;
    background: linear-gradient(135deg, #81c784, #66bb6a);
    color: #fff; text-decoration: none; border-radius: 12px;
    font-weight: 600; font-size: 15px;
    transition: transform .15s ease, box-shadow .15s ease;
  }
  .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(102,187,106,.4); }
  .footer { margin-top: 24px; font-size: 12px; color: #aaa; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">✅</div>
  <h1>Thanh toán thành công</h1>
  <p>
    Mã đơn: <span class="order-code">$order_code</span><br>
    Cô đã nhận được tiền rồi nha! Đang làm nước cho con nè 🥰
  </p>
  <a class="btn" href="https://t.me/belachatbot">💬 Quay lại Box Chat</a>
  <div class="footer">Tiệm trà bé lá &copy; 2026</div>
</div>
</body>
</html>""")


@router.get("/payment/success")
async def payment_success_redirect(
    request: Request,
):
    """
    PayOS redirects the user here when they complete payment on the checkout page.
    We just show a pretty HTML page (the actual DB updates happen in the POST webhook).
    """
    order_code_str = request.query_params.get("orderCode") or request.query_params.get("code")

    if not order_code_str:
        return HTMLResponse("<h2>Missing order code.</h2>", status_code=400)

    try:
        order_code = int(order_code_str)
    except ValueError:
        return HTMLResponse("<h2>Invalid order code.</h2>", status_code=400)

    bot_username = settings.TELEGRAM_BOT_TOKEN.split(":")[0] if ":" in settings.TELEGRAM_BOT_TOKEN else ""
    html = _SUCCESS_HTML_TEMPLATE.safe_substitute(order_code=order_code, bot_username=bot_username)
    return HTMLResponse(html)

# ─── Pretty HTML page shown after user cancels on PayOS ─────────────────────

_CANCEL_HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Đơn hàng đã hủy — Tiệm trà bé lá</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #fce4ec 0%, #fff3e0 100%);
  }
  .card {
    background: #fff;
    border-radius: 20px;
    box-shadow: 0 8px 32px rgba(0,0,0,.08);
    max-width: 420px; width: 90%;
    padding: 48px 32px; text-align: center;
  }
  .icon { font-size: 56px; margin-bottom: 16px; }
  h1 { font-size: 22px; color: #d32f2f; margin-bottom: 8px; }
  p  { color: #555; font-size: 15px; line-height: 1.6; margin-bottom: 24px; }
  .order-code { font-family: monospace; font-weight: 700; color: #333; }
  .btn {
    display: inline-block; padding: 12px 28px;
    background: linear-gradient(135deg, #81c784, #66bb6a);
    color: #fff; text-decoration: none; border-radius: 12px;
    font-weight: 600; font-size: 15px;
    transition: transform .15s ease, box-shadow .15s ease;
  }
  .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(102,187,106,.4); }
  .footer { margin-top: 24px; font-size: 12px; color: #aaa; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">🍵</div>
  <h1>Đơn hàng đã được hủy</h1>
  <p>
    Mã đơn: <span class="order-code">$order_code</span><br>
    Nếu con đổi ý, cứ quay lại nhắn tin cho Cô nhé!
  </p>
  <a class="btn" href="https://t.me/belachatbot">💬 Quay lại Box Chat</a>
  <div class="footer">Tiệm trà bé lá &copy; 2026</div>
</div>
</body>
</html>""")


@router.get("/payment/cancel")
async def payment_cancel_redirect(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    PayOS redirects the user here when they click "Cancel" on the checkout page.
    Updates DB, notifies Owner + User on Telegram, returns a styled HTML page.
    """
    order_code_str = request.query_params.get("orderCode") or request.query_params.get("code")

    if not order_code_str:
        return HTMLResponse("<h2>Missing order code.</h2>", status_code=400)

    try:
        order_code = int(order_code_str)
    except ValueError:
        return HTMLResponse("<h2>Invalid order code.</h2>", status_code=400)

    # 1. Find the order in DB
    stmt = (
        select(Order)
        .where(Order.payos_order_code == order_code)
        .options(selectinload(Order.user))
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        return HTMLResponse("<h2>Order not found.</h2>", status_code=404)

    # 2. Only cancel if still PENDING 
    if order.status == OrderStatus.PENDING:
        try:
            # Safely cancel the order via OrderService, which handles DB updates and flush
            await order_service.cancel_order(
                db, 
                order.id, 
                reason="Khách hủy từ trang thanh toán PayOS", 
                canceled_by_owner=False
            )

            # 3. Clear cart
            if order.user:
                # Use platform.value properly "telegram"
                platform_str = order.user.platform.value if hasattr(order.user.platform, 'value') else "telegram"
                await cart_service.clear_cart(platform_str, order.user.platform_user_id)

            # 4. Notify Owner
            owner_text = (
                f"❌ KHÁCH HỦY ĐƠN (Order #{order.id})\n"
                f"Khách: {order.user.display_name if order.user else 'N/A'}\n"
                f"Tổng: {order.total_price:,.0f}đ\n"
                f"Lý do: Hủy từ trang thanh toán PayOS"
            )
            background_tasks.add_task(telegram_adapter.send_to_owner, text=owner_text)

            # 5. Notify User
            if order.user:
                user_msg = OutgoingMessage(
                    platform_user_id=order.user.platform_user_id,
                    text="Cô thấy con vừa hủy thanh toán rồi nha. Nếu đổi ý thì cứ nhắn lại cho Cô, Cô tạo đơn mới cho con liền! 🍵",
                )
                background_tasks.add_task(telegram_adapter.send_message, user_msg)

            await db.commit()
            
            logger.info(f"PayOS Cancel successfully processed for Order #{order.id}")
        except Exception as e:
            logger.error(f"Error processing PayOS cancel webhook for Order #{order.id}: {e}")
            await db.rollback()
    
    # 6. Render pretty HTML
    bot_username = settings.TELEGRAM_BOT_TOKEN.split(":")[0] if ":" in settings.TELEGRAM_BOT_TOKEN else ""
    # Try to get proper bot username — fallback to empty
    html = _CANCEL_HTML_TEMPLATE.safe_substitute(order_code=order_code, bot_username=bot_username)
    return HTMLResponse(html)

