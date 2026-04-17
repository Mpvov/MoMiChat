"""
Command Service
Handles explicit slash commands (e.g. /start, /cart) using a scalable Dispatcher pattern.
By intercepting commands, we save LLM processing costs and ensure deterministic responses.
"""

from typing import Tuple, List, Dict
import logging
from .cart_service import CartService
from ..utils.formatting import format_bold, format_italic, escape_markdown

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
            "/menu": self.handle_menu
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

        # 2. Check for Internal Owner Actions (Buttons from Owner notifications)
        # SECURITY: Only the owner can trigger these administrative commands
        from ..config import settings
        
        if raw_cmd.startswith("prepare_"):
            if str(user_id) != str(settings.OWNER_CHAT_ID):
                return "Xin lỗi con, chỉ Cô mới có quyền dùng chức năng này nha! 🙅‍♀️", []
            order_id = raw_cmd.replace("prepare_", "")
            return f"✅ Đã ghi nhận đơn hàng số {order_id} đang được chuẩn bị!", []
            
        if raw_cmd.startswith("done_"):
            if str(user_id) != str(settings.OWNER_CHAT_ID):
                return "Xin lỗi con, chỉ Cô mới có quyền dùng chức năng này nha! 🙅‍♀️", []
            order_id = raw_cmd.replace("done_", "")
            return f"✅ Chúc mừng! Đơn hàng số {order_id} đã hoàn tất và giao cho khách!", []

        # 3. NOT A COMMAND -> Let the AI handle it
        return None

    async def handle_start(self, platform: str, user_id: str) -> Tuple[str, List[Dict[str, str]]]:
        text = (
            "Chào con, Cô đây! Cảm ơn con đã ghé Tiệm trà bé lá nha 🥰\n\n"
            "Để order, con cứ nhắn tin tự nhiên như nói chuyện bình thường với Cô:\n"
            "👉 VD: _'Cô ơi cho con 1 hồng trà sữa size M ít đá nha'_\n\n"
            "*Các lệnh tiện ích con có thể dùng báo Cô:*\n"
            "🛒 /cart - Hiện ra các món trong giỏ hàng với lần mua này\n"
            "📖 /start - Gửi lại thông báo hướng dẫn này và xóa giỏ hàng\n\n"
            "Cô cũng có thể làm nút ở dưới cho con bấm nhanh nữa đó!"
        )
        buttons = [
            {"text": "📖 Xem Thực Đơn", "callback_data": "/menu"},
            {"text": "🛒 Giỏ Hàng", "callback_data": "/cart"}
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
        from ..ai.knowledge import MENU_DICT
        
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
        text += f"👉 {format_bold('Con muốn món nào cứ nhắn tin tự nhiên nha')} (vd: {format_italic('cho con 1 ô long nhãn')})!"
        return text, []
