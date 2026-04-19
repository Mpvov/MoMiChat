"""
LangChain tools for the Mom AI Agent.
These functions map directly to our services (Menu Search, Cart, Checkout).
"""

import logging
import traceback
from typing import Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from ..adapters.telegram import TelegramAdapter
from ..config import settings
from ..core.database import async_session_factory
from ..models.order import Order, OrderStatus
from ..services.cart_service import CartService
from ..services.order_service import OrderService
from ..services.payment_service import PaymentService
from ..utils.formatting import escape_markdown
from .knowledge import MENU_DICT, KnowledgeBase

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


class ClearCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")


class ClearCartTool(BaseTool):
    name: str = "clear_cart"
    description: str = (
        "Clear the user's entire shopping cart. Use this BEFORE adding new items "
        "when the user wants to start a completely new order and their cart still "
        "has items from a previous session. "
        "Examples: 'cho con order lại', 'đặt đơn mới', 'order nước đi cô'."
    )
    args_schema: Type[BaseModel] = ClearCartInput

    def _run(self, platform: str, user_id: str) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str) -> str:
        cart_service = CartService()
        cart = await cart_service.get_cart(platform, user_id)
        if not cart:
            return "Giỏ hàng đã trống sẵn, sẵn sàng nhận đơn mới."
        await cart_service.clear_cart(platform, user_id)
        return f"Đã xóa giỏ hàng cũ ({len(cart)} món). Sẵn sàng nhận đơn mới."


class CartItemInput(BaseModel):
    item_id: str = Field(description="Exact DRINK ID from the menu. DO NOT GUESS. You MUST call search_menu first.")
    size: str = Field(description="M or L")
    quantity: int = Field(description="Number of items")
    topping_ids: list[str] = Field(default=[], description="Optional list of topping IDs to attach (e.g., ['TOP01', 'TOP06']). Only use IDs starting with TOP.")

class AddToCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    items: list[CartItemInput] = Field(description="List of drinks to add to the cart. You can add multiple drinks in one call.")


class AddToCartTool(BaseTool):
    name: str = "add_to_cart"
    description: str = (
        "Add one or more DRINKs to the user's cart in a SINGLE BATCH. "
        "Toppings are NOT separate items — pass topping IDs in the `topping_ids` parameter "
        "of each drink to attach them. NEVER call add_to_cart with a topping ID (TOPxx) as item_id. "
        "CRITICAL: ALWAYS use `search_menu` first to find the correct `item_id`. NEVER GUESS THE ID! "
        "CRITICAL: If the user orders multiple drinks, PUT ALL OF THEM in the `items` list in ONE CALL! "
        "CRITICAL: If the drink name ALREADY CONTAINS the topping (e.g. 'Trà Sữa Trân Châu Đen'), DO NOT pass "
        "its ID (e.g. TOP01) in `topping_ids` unless the user explicitly asks for EXTRA."
    )
    args_schema: Type[BaseModel] = AddToCartInput

    def _run(self, platform: str, user_id: str, items: list[dict]) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, items: list[dict] | list[CartItemInput]) -> str:
        logger = logging.getLogger(__name__)
        cart_service = CartService()
        
        responses = []
        for v in items:
            # Handle if given as dict or pydantic model
            item_id = v.item_id if hasattr(v, 'item_id') else v.get('item_id', '')
            size = v.size if hasattr(v, 'size') else v.get('size', 'M')
            qty = v.quantity if hasattr(v, 'quantity') else v.get('quantity', 1)
            tops = v.topping_ids if hasattr(v, 'topping_ids') else v.get('topping_ids', [])
            
            item_id = item_id.upper()
            if item_id not in MENU_DICT:
                responses.append(f"Error: Item {item_id} not found.")
                continue
            
            item = MENU_DICT[item_id]
            
            # Block toppings from being added as standalone items
            if item.get("category", "").lower() == "topping":
                responses.append(
                    f"Error: {item['name']} ({item_id}) is a TOPPING. "
                    f"Pass it in `topping_ids` of a DRINK instead."
                )
                continue
                
            unit_price = item["price_m"] if size.upper() == "M" else item["price_l"]
            
            topping_names = []
            topping_total = 0.0
            for tid in (tops or []):
                tid = tid.upper()
                if tid in MENU_DICT and MENU_DICT[tid].get("category", "").lower() == "topping":
                    topping_names.append(MENU_DICT[tid]["name"])
                    topping_total += MENU_DICT[tid]["price_m"] or 0
            
            final_price = unit_price + topping_total
            
            cart_before = await cart_service.get_cart(platform, user_id)
            cart_after = await cart_service.add_item(
                 platform=platform,
                 user_id=user_id,
                 item_id=item_id,
                 item_name=item["name"],
                 size=size.upper(),
                 quantity=qty,
                 unit_price=final_price,
                 toppings=topping_names
            )
            
            topping_str = f" + {', '.join(topping_names)}" if topping_names else ""
            if len(cart_after) == len(cart_before):
                # Idempotency guard triggered — item was already in cart
                responses.append(f"ALREADY IN CART: {item['name']} (Size {size.upper()}){topping_str}. Do NOT add again.")
            else:
                responses.append(f"Added {qty}x {item['name']} (Size {size.upper()}){topping_str}. Unit: {final_price:,.0f}đ")
            
        return "\n".join(responses)


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


class RemoveFromCartInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    cart_index: int = Field(description="0-based index of the item in the cart to remove. Use 0 for the first item, 1 for the second, etc. YOU MUST CALL view_cart first to know the correct index.")

class RemoveFromCartTool(BaseTool):
    name: str = "remove_from_cart"
    description: str = (
        "Remove an item from the user's cart by its index. "
        "Use this when the user says they don't want an item anymore, "
        "or when you made a mistake adding an item and need to delete it. "
        "Examples: 'bỏ ly trà sữa đi', 'xóa món số 2', 'không lấy kem tươi nữa (nếu kem tươi đi kèm món, phải xóa món đó rồi add lại)'"
    )
    args_schema: Type[BaseModel] = RemoveFromCartInput

    def _run(self, platform: str, user_id: str, cart_index: int) -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, cart_index: int) -> str:
        cart_service = CartService()
        
        cart = await cart_service.get_cart(platform, user_id)
        if not (0 <= cart_index < len(cart)):
            return f"Error: Cart index {cart_index} is invalid. The cart has {len(cart)} items."
            
        item_name = cart[cart_index]["item_name"]
        await cart_service.remove_item(platform, user_id, cart_index)
        
        return f"Thành công! Đã xóa món '{item_name}' (số thứ tự {cart_index}) khỏi giỏ hàng."


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
                
                tel = TelegramAdapter()
                
                # Fetch order item details manually since we just added them in this session but didn't refresh relation
                stmt_refresh = select(Order).where(Order.id == order.id).options(selectinload(Order.items), selectinload(Order.user))
                res_refresh = await db.execute(stmt_refresh)
                refreshed_order = res_refresh.scalar_one()

                msg_text = order_service.format_order_details(refreshed_order, title="⚠️ CÓ ĐƠN MỚI CHỜ THANH TOÁN")
                await tel.send_to_owner(
                    text=msg_text,
                    buttons=[{"text": "❌ Hủy đơn", "data": f"cancel_{order.id}"}]
                )
                
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
        async with async_session_factory() as db:
            order_service = OrderService()
            user = await order_service.get_or_create_user(db, platform, user_id)
            
            # Find the latest SHIPPING order for this user
            stmt = select(Order).where(Order.user_id == user.id, Order.status == OrderStatus.SHIPPING).order_by(desc(Order.created_at)).limit(1)
            result = await db.execute(stmt)
            order = result.scalar_one_or_none()
            
            if not order:
                return "Lỗi: Khách hàng không có đơn hàng nào đang trong trạng thái 'Đang giao' (SHIPPING) để hoàn tất."
            
            order.status = OrderStatus.DONE
            await db.commit()
            
            # Notify Owner
            tel = TelegramAdapter()
            await tel.send_to_owner(f"\u2705 Đơn hàng số {order.id} của khách {user.display_name} đã báo ĐÃ NHẬN HÀNG (qua chat)!")
            
            return f"Thành công! Đã chuyển trạng thái đơn {order.id} sang HOÀN TẤT (DONE)."


class CancelOrderInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")
    reason: str = Field(default="Khách hàng hủy đơn", description="Reason for cancellation (optional)")


class CancelOrderTool(BaseTool):
    name: str = "cancel_order"
    description: str = (
        "Cancel the user's most recent PENDING order. "
        "This will invalidate the PayOS payment link and mark the order as CANCELED. "
        "Use when the customer explicitly asks to cancel their order or checkout."
    )
    args_schema: Type[BaseModel] = CancelOrderInput

    def _run(self, platform: str, user_id: str, reason: str = "Khách hàng hủy đơn") -> str:
        return "Not implemented synchronously."

    async def _arun(self, platform: str, user_id: str, reason: str = "Khách hàng hủy đơn") -> str:
        logger = logging.getLogger(__name__)
        logger.info(f"[CancelOrder] called: user={platform}:{user_id}, reason={reason}")

        async with async_session_factory() as db:
            order_service = OrderService()
            payment_service = PaymentService()
            cart_service = CartService()

            # 1. Find the latest PENDING order
            order = await order_service.get_latest_pending_order(db, platform, user_id)

            if not order:
                return "Không có đơn hàng nào đang chờ thanh toán để hủy."

            # 2. Cancel order using unified flow
            success = await order_service.cancel_order(db, order.id, reason, canceled_by_owner=False)
            if not success:
               return "Đơn hàng không thể hủy lúc này."

            # 3. Clear user cart
            await cart_service.clear_cart(platform, user_id)

            # 4. Notify Owner
            telegram = TelegramAdapter()
            await telegram.send_to_owner(
                text=(
                    f"❌ KHÁCH HỦY ĐƠN (Order #{order.id})\n"
                    f"Khách: {order.user.display_name or 'N/A'}\n"
                    f"Tổng: {order.total_price:,.0f}đ\n"
                    f"Lý do: {reason}"
                ),
            )

            await db.commit()

            return (
                f"Đã hủy đơn hàng #{order.id} thành công. "
                f"Link thanh toán đã bị vô hiệu hóa và giỏ hàng đã được xóa. "
                f"Hãy thông báo cho khách hàng rằng đơn đã được hủy."
            )

