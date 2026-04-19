from typing import Dict, List, Tuple

import logging
from sqlalchemy import select

from ..adapters.base import OutgoingMessage
from ..adapters.telegram import TelegramAdapter
from ..ai.knowledge import MENU_DICT
from ..config import settings
from ..core.database import async_session_factory
from ..models.order import Order, OrderStatus
from ..models.user import User
from ..services.cart_service import CartService
from ..services.order_service import OrderService
from ..utils.formatting import (
    escape_markdown,
    format_bold,
    format_italic,
)

logger = logging.getLogger(__name__)

class CommandService:
    def __init__(self, cart_service: CartService):
        self.cart_service = cart_service
        # Bảng điều phối Lệnh (Routing Table)
        # Bất kỳ lệnh mới nào chỉ cần add key vào đây
        self.handlers = {
            "/start": self.handle_start,
            "/help": self.handle_start,
            "/cart": self.handle_cart,
            "/menu": self.handle_menu,
            "/guide": self.handle_guide
        }

    async def execute(self, command: str, platform: str, user_id: str) -> Tuple[str, List[Dict[str, str]]] | None:
        """
        Dispatches the command to the appropriate handler.
        Returns a tuple of (reply_text, buttons) or None if NOT a command.
        """
        raw_cmd = command.strip().lower()
        
        # 1. Check for standard /commands
        if raw_cmd.startswith("/"):
            cmd_key = raw_cmd.split(" ")[0]
            if cmd_key in self.handlers:
                handler = self.handlers[cmd_key]
                return await handler(platform, user_id)
            return f"Lệnh {cmd_key} hiện chưa hỗ trợ con nha. Con thử gõ phím hỏi cô xem sao 😅", []

        # 2. Check for Internal Actions (Buttons from Owner or Customer)
        async def process_order_status(order_id_str: str, target_status: OrderStatus, allowed_user_id: str | None, success_owner_msg: str, success_user_msg: str, user_button: dict | None = None, owner_button: dict | None = None) -> Tuple[str, List[Dict[str, str]]]:
            # Validation
            if allowed_user_id and str(user_id) != allowed_user_id:
                return "Xin lỗi, con không có quyền dùng chức năng này nha! 🙅‍♀️", []
            
            try:
                order_id = int(order_id_str)
            except ValueError:
                return "Mã đơn hàng không hợp lệ.", []

            async with async_session_factory() as db:
                stmt = select(Order).where(Order.id == order_id)
                res = await db.execute(stmt)
                order = res.scalar_one_or_none()
                
                if not order:
                    return f"Không tìm thấy đơn hàng số {order_id}!", []
                
                # Check permission for user (if they are the customer marking DONE)
                if target_status == OrderStatus.DONE and allowed_user_id is None:
                    # Fetch user to ensure the one clicking is the owner of the order
                    order_service = OrderService()
                    user = await order_service.get_or_create_user(db, platform, user_id)
                    if order.user_id != user.id:
                        return "Kia là đơn của người khác, con không được bấm đâu nha!", []
                
                order.status = target_status
                await db.commit()
                
                # Notifications
                tel = TelegramAdapter()
                
                if target_status in [OrderStatus.PREPARING, OrderStatus.SHIPPING]:
                    # Owner triggered, notify user
                    user_stmt = select(User).where(User.id == order.user_id)
                    user_res = await db.execute(user_stmt)
                    cust = user_res.scalar_one_or_none()
                    if cust:
                        buttons_list = [user_button] if user_button else []
                        cust_msg = OutgoingMessage(
                            platform_user_id=cust.platform_user_id,
                            text=success_user_msg,
                            buttons=buttons_list if buttons_list else None,
                        )
                        await tel.send_message(cust_msg)
                
                # If Target is DONE and user triggered it, notify owner
                if target_status == OrderStatus.DONE and allowed_user_id is None:
                    await tel.send_to_owner(success_owner_msg)
                    return success_user_msg, []
                
                return success_owner_msg, [owner_button] if owner_button else []

        if raw_cmd.startswith("prepare_"):
            oid = raw_cmd.replace("prepare_", "")
            return await process_order_status(
                order_id_str=oid,
                target_status=OrderStatus.PREPARING,
                allowed_user_id=str(settings.owner_chat_id_clean),
                success_owner_msg=f"✅ Đã chốt. Đang chuẩn bị đơn {oid}!",
                success_user_msg=f"Cô đang đi pha nước cho con rồi nha!",
                owner_button={"text": "🚚 Bắt đầu giao (Shipping)", "callback_data": f"shipping_{oid}"}
            )
            
        if raw_cmd.startswith("shipping_"):
            oid = raw_cmd.replace("shipping_", "")
            return await process_order_status(
                order_id_str=oid,
                target_status=OrderStatus.SHIPPING,
                allowed_user_id=str(settings.owner_chat_id_clean),
                success_owner_msg=f"✅ Đã đổi trạng thái đơn {oid} thành ĐANG GIAO!",
                success_user_msg=f"Nước đang trên đường tới chỗ con nè (Đơn #{oid}). Khi nào nhận được nhớ bấm nút báo Cô nha!",
                user_button={"text": "✅ Đã nhận được nước", "callback_data": f"done_{oid}"}
            )

        if raw_cmd.startswith("done_"):
            oid = raw_cmd.replace("done_", "")
            # allowed_user_id=None means any user can click, but we check order ownership inside
            return await process_order_status(
                order_id_str=oid,
                target_status=OrderStatus.DONE,
                allowed_user_id=None,
                success_owner_msg=f"✅ Đơn hàng số {oid} đã giao thành công và khách báo ĐÃ NHẬN HÀNG!",
                success_user_msg=f"Cảm ơn con nhiều nghen, uống ngon mai mốt ủng hộ Cô tiếp nha! 😋 Đơn #{oid}"
            )

        if raw_cmd.startswith("cancel_"):
            oid = raw_cmd.replace("cancel_", "")
            if str(user_id) != str(settings.owner_chat_id_clean):
                return "Xin lỗi, con không có quyền dùng chức năng này nha! 🙅‍♀️", []
                
            try:
                order_id = int(oid)
            except ValueError:
                return "Mã đơn hàng không hợp lệ.", []
                
            order_service = OrderService()
            async with async_session_factory() as db:
                success = await order_service.cancel_order(
                    db=db, 
                    order_id=order_id, 
                    reason="Chủ quán từ chối nhận đơn", 
                    canceled_by_owner=True
                )
                if success:
                    await db.commit()
                    return f"✅ Đã hủy đơn {order_id} thành công và báo cho khách!", []
                else:
                    return f"❌ Trạng thái đơn {order_id} hiện tại không cho phép hủy (Chỉ hủy được đơn đang chờ thanh toán).", []

        # 3. NOT A COMMAND -> Let the AI handle it
        return None

    async def handle_start(self, platform: str, user_id: str) -> Tuple[str, List[Dict[str, str]]]:
        text = (
            "Chào con, Cô đây! Cảm ơn con đã ghé Tiệm trà bé lá nha 🥰\n\n"
            "Để order nhanh nhất, con cứ nhắn tin tự nhiên như nói chuyện bình thường với Cô:\n"
            "👉 VD: _'Cô ơi cho con 1 hồng trà sữa size M ít đá nha'_\n\n"
            "*Các lệnh tiện ích con có thể dùng báo Cô:*\n"
            "📖 /guide - Xem hướng dẫn cách đặt nước chi tiết\n"
            "🛒 /cart - Hiện ra các món trong giỏ hàng\n"
            "✨ /menu - Xem Thực Đơn của Tiệm\n"
            "/start - Gửi lại thông báo này và xóa giỏ hàng\n\n"
            "Cô cũng có các nút ở dưới cho con bấm nhanh nữa đó!"
        )
        buttons = [
            {"text": "📖 Xem Hướng dẫn", "callback_data": "/guide"},
            {"text": "✨ Xem Menu", "callback_data": "/menu"},
            {"text": "🛒 Giỏ Hàng", "callback_data": "/cart"}
        ]
        return text, buttons

    async def handle_guide(self, platform: str, user_id: str) -> Tuple[str, List[Dict[str, str]]]:
        text = (
            "📖 *HƯỚNG DẪN ĐẶT NƯỚC TẠI MOMICHAT*\n\n"
            "*Bước 1: Chọn món con thích* 🥤\n"
            "Con cứ nhắn tin tự nhiên với Cô như đang chat với người thân vậy đó!\n"
            "👉 VD: _'Cô ơi cho con 1 Trà Đào Sả size L ít đường nha'_\n"
            "Hoặc con bấm nút *Xem Menu* để chọn món nhanh nhé.\n\n"
            "*Bước 2: Chốt đơn & Cung cấp thông tin* 📝\n"
            "Sau khi chọn xong, con gõ \"Thanh toán\" hoặc bấm nút *Thanh Toán*.\n"
            "Cô sẽ hỏi Số điện thoại và Địa chỉ để Shipper dễ tìm thấy con. Con nhớ nhắn cho Cô chính xác nha!\n\n"
            "*Bước 3: Thanh toán an toàn* 💳\n"
            "Cô sẽ gửi con một link thanh toán *PayOS* (ngân hàng chính thống).\n"
            "Con bấm vào link, chuyển khoản xong là hệ thống sẽ tự báo cho Cô ngay, không cần gửi ảnh bill đâu nè!\n\n"
            "*Bước 4: Theo dõi đơn hàng* 🚚\n"
            "Sau khi thanh toán, Cô sẽ cập nhật trạng thái đơn:\n"
            "1️⃣ *Đang pha chế* ☕️: Cô đang vào bếp làm nước cho con.\n"
            "2️⃣ *Đang giao hàng* 🛵: Shipper đang trên đường tới.\n"
            "3️⃣ *Hoàn thành* ✅: Khi nhận được nước, con bấm nút *\"Đã nhận được nước\"* để Cô yên tâm nhé! Hoặc nói Cô một tiếng nhé 🥰"
        )
        buttons = [
            {"text": "✨ Xem Menu Ngay", "callback_data": "/menu"}
        ]
        return text, buttons

    async def handle_cart(self, platform: str, user_id: str) -> Tuple[str, List[Dict[str, str]]]:
        summary = await self.cart_service.cart_summary(platform, user_id)
        cart = await self.cart_service.get_cart(platform, user_id)
        
        buttons = []
        if cart:
            buttons.append({"text": "💳 Thanh Toán Ngay", "callback_data": "Thanh toán cho con"})
            
        return f"Giỏ hàng của con nè:\n\n{summary}", buttons

    async def handle_menu(self, platform: str, user_id: str) -> Tuple[str, List[Dict[str, str]]]:
        if not MENU_DICT:
            return "Úi, Cô đang lấy menu trong bếp, con đợi xíu nha (Menu rỗng)!", []
            
        # Phân nhóm theo `category`
        categories = {}
        for item_id, item in MENU_DICT.items():
            if item.get("available", True):
                cat = item.get("category", "🍵 Đồ Uống Khác")
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)
                
        menu_lines = [f"✨ {format_bold('THỰC ĐƠN TIỆM TRÀ BÉ LÁ')} ✨\n"]
        for cat, items in categories.items():
            menu_lines.append(format_bold(f"— {cat.upper()} —"))
            for item in items:
                prices = []
                if item.get("price_m"):
                    prices.append(f"M: {int(item['price_m'])}")
                if item.get("price_l"):
                    prices.append(f"L: {int(item['price_l'])}")
                
                price_str = " | ".join(prices) if prices else "Liên hệ"
                
                menu_lines.append(f"• {format_bold(item['name'])}")
                if item.get('description'):
                    menu_lines.append(f"   {format_italic(item['description'])}")
                menu_lines.append(f"   💸 {price_str}")
            menu_lines.append("") # Khoảng trắng giữa các mục
                
        text = "\n".join(menu_lines)
        text += f"👉 {format_bold('Con muốn món nào cứ nhắn tin tự nhiên nha')} (vd: {format_italic('cho con 1 trà sữa trân châu đen')})!"
        return text, []
