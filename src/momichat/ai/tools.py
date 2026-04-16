"""
LangChain tools for the Mom AI Agent.
These functions map directly to our services (Menu Search, Cart, Checkout).
"""

from typing import Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from .knowledge import MENU_DICT, KnowledgeBase

# Assume knowledge base is injected or initialized cleanly in a real app
kb = KnowledgeBase()


class SearchMenuInput(BaseModel):
    query: str = Field(description="The customer's question or item description")


class SearchMenuTool(BaseTool):
    name: str = "search_menu"
    description: str = "Use this to search the menu when a user asks for a drink or recommends something."
    args_schema: Type[BaseModel] = SearchMenuInput

    def _run(self, query: str) -> str:
        if query.lower() in ["", "all", "menu", "tất cả"]:
            if not MENU_DICT:
                return "Menu hiện đang trống (chưa load)."
            return "\n".join([f"ID: {k} | Tên: {v['name']} | Giá: {v['price_m']}đ (M)/{v['price_l']}đ (L)" for k, v in MENU_DICT.items()])
            
        results = kb.search_menu(query)
        if not results:
            return "Không tìm thấy món nào phù hợp."
        return "\n".join([f"ID: {r['item_id']}, Info: {r['snippet']}" for r in results])


class AddToCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    item_id: str = Field(description="Exact ID from the menu (e.g., TS01)")
    size: str = Field(description="M or L")
    quantity: int = Field(description="Number of items")


class AddToCartTool(BaseTool):
    name: str = "add_to_cart"
    description: str = "Use this to add items to the user's cart AFTER they confirm what they want."
    args_schema: Type[BaseModel] = AddToCartInput

    def _run(self, platform: str, user_id: str, item_id: str, size: str, quantity: int) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, item_id: str, size: str, quantity: int) -> str:
        from ..services.cart_service import CartService
        
        if item_id not in MENU_DICT:
            return f"Error: Item {item_id} not found."
            
        cart_service = CartService()
        item = MENU_DICT[item_id]
        unit_price = item["price_m"] if size.upper() == "M" else item["price_l"]
        
        await cart_service.add_item(
             platform=platform,
             user_id=user_id,
             item_id=item_id,
             item_name=item["name"],
             size=size.upper(),
             quantity=quantity,
             unit_price=unit_price
        )
        return f"Added {quantity}x {item['name']} (Size {size.upper()}) to cart."


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
                order = await order_service.create_order(db, user.id, cart_items)
                
                if payment_service.payos is None:
                    return "Lỗi: Thanh toán chưa được thiết lập (thiếu PayOS Key)."
                    
                description = f"Thanh toan DON {order.id}"
                payment_link = await payment_service.create_payment_link(order.id, order.total_price, description)
                
                order.payos_order_code = payment_link["orderCode"]
                await db.commit()
                
                # Clear cart upon successful order creation
                await cart_service.clear_cart(platform, user_id)
                
                return f"Thành công! Hãy gửi cho user link thanh toán này: {payment_link['checkoutUrl']}"
            except Exception as e:
                await db.rollback()
                import traceback
                traceback.print_exc()
                return f"Lỗi tạo đơn hàng hoặc mã thanh toán: {str(e)}"
