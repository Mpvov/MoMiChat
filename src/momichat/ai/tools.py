"""
LangChain tools for the Mom AI Agent.
These functions map directly to our services (Menu Search, Cart, Checkout).
"""

from typing import Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from .knowledge import MENU_DICT, KnowledgeBase
from ..utils.formatting import escape_markdown

# Assume knowledge base is injected or initialized cleanly in a real app
kb = KnowledgeBase()


class SearchMenuInput(BaseModel):
    query: str = Field(description="The customer's question or item description. Use 'all' to list everything, 'drinks' for drinks only, 'toppings' for toppings only.")


class SearchMenuTool(BaseTool):
    name: str = "search_menu"
    description: str = "Use this to search the menu when a user asks for a drink or recommends something."
    args_schema: Type[BaseModel] = SearchMenuInput

    def _run(self, query: str) -> str:
        if query.lower() in ["", "all", "menu", "tất cả"]:
            if not MENU_DICT:
                return "Menu hiện đang trống (chưa load)."
            return self._format_menu(MENU_DICT)
        if query.lower() in ["drinks", "đồ uống"]:
            filtered = {k: v for k, v in MENU_DICT.items() if v.get('category', '').lower() != 'topping'}
            return self._format_menu(filtered)
        if query.lower() in ["toppings", "topping"]:
            filtered = {k: v for k, v in MENU_DICT.items() if v.get('category', '').lower() == 'topping'}
            return self._format_menu(filtered)
            
        results = kb.search_menu(query)
        if not results:
            return "Không tìm thấy món nào phù hợp."
        return "\n".join([f"ID: {r['item_id']}, Info: {r['snippet']}" for r in results])

    @staticmethod
    def _format_menu(items: dict) -> str:
        lines = []
        for k, v in items.items():
            tag = "[TOPPING]" if v.get('category', '').lower() == 'topping' else "[DRINK]"
            lines.append(f"{tag} ID: {k} | Tên: {v['name']} | Giá: {v['price_m']}đ (M)/{v['price_l']}đ (L)")
        return "\n".join(lines)


class ViewCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")


class ViewCartTool(BaseTool):
    name: str = "view_cart"
    description: str = (
        "View the user's current shopping cart from the database. "
        "ALWAYS use this tool when the user asks about their cart, "
        "what they have ordered, or wants to review before checkout. "
        "Do NOT rely on conversation memory for cart contents."
    )
    args_schema: Type[BaseModel] = ViewCartInput

    def _run(self, platform: str, user_id: str) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str) -> str:
        from ..services.cart_service import CartService

        cart_service = CartService()
        cart = await cart_service.get_cart(platform, user_id)

        if not cart:
            return "Giỏ hàng hiện đang trống."

        lines = []
        total = 0.0
        for i, item in enumerate(cart):
            subtotal = item["unit_price"] * item["quantity"]
            total += subtotal
            topping_str = f" + {', '.join(item['toppings'])}" if item.get("toppings") else ""
            lines.append(
                f"[{i}] {item['item_name']} (Size {item['size']}){topping_str} "
                f"x{item['quantity']} = {subtotal:,.0f}đ"
            )
        lines.append(f"TOTAL: {total:,.0f}đ")
        return "\n".join(lines)


class AddToCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    item_id: str = Field(description="Exact DRINK ID from the menu (e.g., TS01). Must NOT be a topping ID (TOPxx).")
    size: str = Field(description="M or L")
    quantity: int = Field(description="Number of items")
    topping_ids: list[str] = Field(default=[], description="Optional list of topping IDs to attach (e.g., ['TOP01', 'TOP06']). Only use IDs starting with TOP.")


class AddToCartTool(BaseTool):
    name: str = "add_to_cart"
    description: str = (
        "Add a DRINK to the user's cart. Toppings are NOT separate items — "
        "pass topping IDs in the `topping_ids` parameter to attach them to THIS drink. "
        "NEVER call add_to_cart with a topping ID (TOPxx) as item_id."
    )
    args_schema: Type[BaseModel] = AddToCartInput

    def _run(self, platform: str, user_id: str, item_id: str, size: str, quantity: int, topping_ids: list[str] | None = None) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, item_id: str, size: str, quantity: int, topping_ids: list[str] | None = None) -> str:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[AddToCart] called: item_id={item_id}, size={size}, qty={quantity}, toppings={topping_ids}, user={platform}:{user_id}")
        
        from ..services.cart_service import CartService
        
        item_id = item_id.upper()
        if item_id not in MENU_DICT:
            return f"Error: Item {item_id} not found."
        
        item = MENU_DICT[item_id]
        
        # Block toppings from being added as standalone items
        if item.get("category", "").lower() == "topping":
            return (
                f"Error: {item['name']} ({item_id}) is a TOPPING, not a drink. "
                f"Do NOT add toppings as separate items. Instead, pass topping IDs "
                f"in the `topping_ids` parameter when adding the DRINK."
            )
            
        cart_service = CartService()
        unit_price = item["price_m"] if size.upper() == "M" else item["price_l"]
        
        # Resolve topping names and add their prices
        topping_names = []
        topping_total = 0.0
        for tid in (topping_ids or []):
            tid = tid.upper()
            if tid in MENU_DICT and MENU_DICT[tid].get("category", "").lower() == "topping":
                topping_names.append(MENU_DICT[tid]["name"])
                topping_total += MENU_DICT[tid]["price_m"] or 0
        
        final_price = unit_price + topping_total
        
        await cart_service.add_item(
             platform=platform,
             user_id=user_id,
             item_id=item_id,
             item_name=item["name"],
             size=size.upper(),
             quantity=quantity,
             unit_price=final_price,
             toppings=topping_names
        )
        
        topping_str = f" + {', '.join(topping_names)}" if topping_names else ""
        return f"Added {quantity}x {item['name']} (Size {size.upper()}){topping_str} to cart. Unit price: {final_price:,.0f}đ"


class AddToppingToCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    cart_index: int = Field(description="0-based index of the drink in the cart to add topping to. Use 0 for the first item, 1 for the second, etc.")
    topping_id: str = Field(description="Topping ID to add (e.g., TOP06 for Kem Tươi)")


class AddToppingToCartTool(BaseTool):
    name: str = "add_topping_to_cart_item"
    description: str = (
        "Add a topping to a drink that is ALREADY in the user's cart. "
        "Use this when the user wants to add a topping to an existing order, "
        "e.g. 'thêm kem tươi' when they already have a drink in cart. "
        "Use cart_index=0 for the first drink, 1 for the second, etc."
    )
    args_schema: Type[BaseModel] = AddToppingToCartInput

    def _run(self, platform: str, user_id: str, cart_index: int, topping_id: str) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, cart_index: int, topping_id: str) -> str:
        from ..services.cart_service import CartService

        topping_id = topping_id.upper()
        if topping_id not in MENU_DICT:
            return f"Error: Topping {topping_id} not found in menu."

        topping = MENU_DICT[topping_id]
        if topping.get("category", "").lower() != "topping":
            return f"Error: {topping['name']} ({topping_id}) is not a topping."

        cart_service = CartService()
        topping_price = topping["price_m"] or 0

        result = await cart_service.add_topping_to_item(
            platform=platform,
            user_id=user_id,
            cart_index=cart_index,
            topping_name=topping["name"],
            topping_price=topping_price,
        )

        if result is None:
            return f"Error: Cart index {cart_index} is invalid. Check the cart first."

        updated_item = result[cart_index]
        return (
            f"Added topping '{topping['name']}' (+{topping_price:,.0f}đ) to "
            f"'{updated_item['item_name']}'. New unit price: {updated_item['unit_price']:,.0f}đ"
        )


class CheckoutInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")


class CheckoutTool(BaseTool):
    name: str = "checkout"
    description: str = "Use this when the user is ready to pay. It generates a PayOS link."
    args_schema: Type[BaseModel] = CheckoutInput

    def _run(self, platform: str, user_id: str) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str) -> str:
        from ..services.cart_service import CartService
        from ..services.order_service import OrderService
        from ..services.payment_service import PaymentService
        from ..core.database import async_session_factory
        
        cart_service = CartService()
        order_service = OrderService()
        payment_service = PaymentService()
        
        cart_items = await cart_service.get_cart(platform, user_id)
        if not cart_items:
            return "Giỏ hàng của con đang trống, hãy gọi món trước nha!"
            
        async with async_session_factory() as db:
            try:
                user = await order_service.get_or_create_user(db, platform, user_id)
                
                # Ensure we have phone and address
                if not user.phone or not user.address:
                    return "Lỗi: Khách hàng chưa cung cấp đủ Số điện thoại và Địa chỉ. Hãy gọi `update_delivery_info` trước khi thanh toán."
                
                order = await order_service.create_order(db, user.id, cart_items)
                
                # Copy delivery info from User to Order
                order.delivery_phone = user.phone
                order.delivery_address = user.address
                
                if payment_service.payos is None:
                    return "Lỗi: Thanh toán chưa được thiết lập (thiếu PayOS Key)."
                    
                description = f"Thanh toan DON {order.id}"
                payment_link = await payment_service.create_payment_link(order.id, order.total_price, description)
                
                order.payos_order_code = payment_link["orderCode"]
                await db.commit()
                
                return f"Thành công! Hãy gửi cho user link thanh toán này: {payment_link['checkoutUrl']}"
            except Exception as e:
                await db.rollback()
                import traceback
                traceback.print_exc()
                return f"Lỗi tạo đơn hàng hoặc mã thanh toán: {str(e)}"

class UpdateDeliveryInfoInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    phone: str = Field(description="Customer's phone number")
    address: str = Field(description="Customer's delivery address")

class UpdateDeliveryInfoTool(BaseTool):
    name: str = "update_delivery_info"
    description: str = "Use this to save or update the customer's phone number and delivery address before checkout."
    args_schema: Type[BaseModel] = UpdateDeliveryInfoInput

    def _run(self, platform: str, user_id: str, phone: str, address: str) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, phone: str, address: str) -> str:
        from ..services.order_service import OrderService
        from ..core.database import async_session_factory

        order_service = OrderService()
        async with async_session_factory() as db:
            user = await order_service.get_or_create_user(db, platform, user_id)
            user.phone = phone
            user.address = address
            await db.commit()
            return f"Đã lưu thành công SDT: {phone} và Địa chỉ: {address} cho khách."

class MarkOrderDoneInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")

class MarkOrderDoneTool(BaseTool):
    name: str = "mark_order_done"
    description: str = "Use this when the customer explicitly says they received the drink or arrived at the shop to pick it up. It marks their active shipping order as DONE."
    args_schema: Type[BaseModel] = MarkOrderDoneInput

    def _run(self, platform: str, user_id: str) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str) -> str:
        from ..services.order_service import OrderService
        from ..services.command_service import CommandService
        from ..services.cart_service import CartService
        from ..core.database import async_session_factory
        from sqlalchemy import select, desc
        from ..models.order import Order, OrderStatus

        async with async_session_factory() as db:
            order_service = OrderService()
            user = await order_service.get_or_create_user(db, platform, user_id)
            
            # Find the latest SHIPPING order for this user
            stmt = select(Order).where(Order.user_id == user.id, Order.status == OrderStatus.SHIPPING).order_by(desc(Order.created_at)).limit(1)
            result = await db.execute(stmt)
            order = result.scalar_one_or_none()
            
            if not order:
                return "Lỗi: Khách hàng không có đơn hàng nào đang trong trạng thái 'Đang giao' (SHIPPING) để hoàn tất."
            
            # Mark as done using command service logic
            # To avoid circular imports and keep logic DRY, we'll manually update here and trigger notification
            from ..adapters.telegram import TelegramAdapter
            from ..models.message import OutgoingMessage
            from ..config import settings
            import logging
            
            order.status = OrderStatus.DONE
            await db.commit()
            
            # Notify Owner
            tel = TelegramAdapter(settings.TELEGRAM_BOT_TOKEN)
            await tel.send_to_owner(f"✅ Đơn hàng số {order.id} của khách {user.display_name} đã báo ĐÃ NHẬN HÀNG (qua chat)!")
            
            return f"Thành công! Đã chuyển trạng thái đơn {order.id} sang HOÀN TẤT (DONE)."
