"""
AI Agent manager implementing the Factory Pattern to swap LLM providers 
and orchestrate LangChain Agent Executors with memory.
"""

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..config import settings
from .tools import AddToCartTool, AddToppingToCartTool, CheckoutTool, SearchMenuTool, ViewCartTool, UpdateDeliveryInfoTool, MarkOrderDoneTool

SYSTEM_PROMPT = """
You are the AI clone of an extremely friendly and caring mother who owns "Tiệm trà bé lá" Milk Tea Shop. 
Speak in Vietnamese. Call yourself "Cô" and call the customer "con".
Your task is to take orders, answer menu questions, and trigger the checkout when the customer is ready.
If the requested item is strange or doesn't exist, politely suggest something else from the menu.

CRITICAL RULES:
1. When asked for the menu, ALWAYS use the `search_menu` tool with query "all" to get the items, and directly WRITE OUT the actual drink names and prices in your chat message. Do not say "Here is the menu" without actually listing the items you received from the tool.
2. Available tools: search_menu, add_to_cart, checkout. Use them appropriately.
3. HẠN CHẾ NÚT BẤM (BUTTONS): TUYỆT ĐỐI KHÔNG tự tạo nút cho các hành động chung (như "Xem menu", "Thanh toán"). Hãy để khách hàng nhắn tin tự nhiên. CHỈ dùng nút JSON cho các lựa chọn bắt buộc (VD: chọn Size M/L, Đá/Đường).
   Cấu trúc JSON chuẩn:
   ```json
   {
     "text": "Lời nhắn (dùng *Markdown*)",
     "buttons": [{"text": "Size M", "callback_data": "size:M"}]
   }
   ```
4. ĐỊNH DẠNG VĂN BẢN: Chỉ dùng `*in đậm*` (1 dấu sao) và `_in nghiêng_` (1 gạch dưới). TUYỆT ĐỐI KHÔNG dùng `**` hoặc HTML tags.
5. THOÁT KÝ TỰ (ESCAPE): Phải dùng `\\*` và `\\_` để thoát các ký tự này nếu không dùng để định dạng văn bản.
6. TOPPING RULE: Topping không bán riêng. Thêm vào ly mới dùng `add_to_cart`. Thêm vào ly có sẵn dùng `add_topping_to_cart_item`.
7. CART RULE: Luôn gọi `view_cart` khi khách hỏi về giỏ hàng. Không tự đoán.
8. GIAO HÀNG (DELIVERY): 
   - Tuân thủ SYSTEM CONTEXT chứa SĐT và Địa chỉ của khách.
   - Nếu khách CHƯA CÓ SĐT hoặc địa chỉ, BẮT BUỘC hỏi xin rồi gọi tool `update_delivery_info` TRƯỚC KHI gọi `checkout`.
   - Nếu ĐÃ CÓ, hãy xin xác nhận trước khi checkout (VD: Mẹ vẫn giao tới địa chỉ X, số Y như cũ nha con?).
   - Nếu khách trả lời "Đã nhận được hàng" / "Nước tới rồi", BẮT BUỘC gọi tool `mark_order_done` để hoàn tất đơn hàng đang giao.
"""

class AgentFactory:
    @staticmethod
    def create_llm():
        """Factory method to get the active LLM based on environment."""
        if settings.DEFAULT_LLM_PROVIDER.lower() == "gemini":
            return ChatGoogleGenerativeAI(
                model="gemini-3.1-flash-lite-preview", 
                temperature=0.7,
                google_api_key=settings.GEMINI_API_KEY
            )
        else:
            return ChatOpenAI(
                model="gpt-4o-mini", 
                temperature=0.7,
                api_key=settings.OPENAI_API_KEY
            )

    @staticmethod
    def create_agent_executor():
        llm = AgentFactory.create_llm()
        tools = [SearchMenuTool(), ViewCartTool(), AddToCartTool(), AddToppingToCartTool(), CheckoutTool(), UpdateDeliveryInfoTool(), MarkOrderDoneTool()]
        return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)

# Global singleton executor for MVP
agent_executor = AgentFactory.create_agent_executor()

async def process_user_message(platform: str, user_id: str, message: str, chat_history: list) -> tuple[str, list, list]:
    """Executes the agent logic for an incoming message, returning text, history, and buttons."""
    
    from ..services.order_service import OrderService
    from ..core.database import async_session_factory
    from sqlalchemy import select
    from ..models.order import Order, OrderStatus
    
    order_service = OrderService()
    phone = "Chưa có"
    address = "Chưa có"
    shipping_order = False
    
    async with async_session_factory() as db:
        user = await order_service.get_or_create_user(db, platform, user_id)
        if user.phone: phone = user.phone
        if user.address: address = user.address
        
        stmt = select(Order).where(Order.user_id == user.id, Order.status == OrderStatus.SHIPPING).limit(1)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            shipping_order = True

    # We silently inject the exact user parameters and tool constraints into the message 
    # so the AI knows exactly how to invoke the tools without hallucinating.
    enriched_message = (
        f"[SYSTEM CONTEXT: platform='{platform}', user_id='{user_id}'. "
        f"User Data in DB -> Phone: {phone}, Address: {address}, Has Active Shipping Order: {shipping_order}\n"
        f"CRITICAL: If the user is ordering drinks, you MUST call the `add_to_cart` tool for EACH DISTINCT drink! "
        f"NEVER call `add_to_cart` more than ONCE for the same drink. If the user wants 2 of the same drink, set quantity=2 in ONE call. "
        f"Toppings (TOPxx) are NOT drinks. For NEW orders with toppings, pass topping_ids in `add_to_cart`. "
        f"To add a topping to a drink ALREADY IN CART, use `add_topping_to_cart_item` with the cart_index.]\n\n"
        f"Customer Message: {message}"
    )
    
    messages = chat_history + [HumanMessage(content=enriched_message)]
    
    response = await agent_executor.ainvoke({"messages": messages}, config={"configurable": {"thread_id": user_id}})
    
    # LangGraph returns a dict with "messages" list.
    # The last message is the AI's response.
    full_messages = response["messages"]
    final_message = full_messages[-1]
    
    content = final_message.content
    
    import json
    import re
    
    clean_text = str(content).strip()
    buttons = []
    
    # Strip markdown code block wrapper if exists
    if clean_text.startswith("```"):
        lines = clean_text.split('\n')
        if len(lines) >= 2:
            clean_text = '\n'.join(lines[1:-1]).strip()

    def _repair_json_buttons(text: str) -> str:
        """Fixes common AI JSON errors, e.g., missing brackets around buttons."""
        # Find "buttons": {obj1}, {obj2} and wrap in []
        pattern = r'("buttons"\s*:\s*)([^{]*{[^}]*}(?:\s*,\s*{[^}]*})*)'
        def wrap_in_brackets(match):
            prefix = match.group(1)
            content = match.group(2).strip()
            if not content.startswith('['):
                return f'{prefix}[{content}]'
            return match.group(0)
        return re.sub(pattern, wrap_in_brackets, text)

    # --- JSON extraction (handles both pure JSON and embedded JSON) ---
    def _try_parse_json_response(text: str) -> tuple[str, list] | None:
        """Attempt to extract {"text": ..., "buttons": [...]} from the AI output."""
        text = _repair_json_buttons(text)
        
        # Strategy 1: The whole string is valid JSON
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "text" in parsed:
                btn = parsed.get("buttons", [])
                if isinstance(btn, dict):
                    btn = [btn]
                return parsed["text"], btn
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: JSON is embedded within prose text — find the outermost {...}
        # This handles cases where the AI writes text before/after the JSON block
        brace_start = text.find('{')
        if brace_start != -1:
            # Find the matching closing brace
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        json_candidate = text[brace_start:i + 1]
                        try:
                            parsed = json.loads(json_candidate)
                            if isinstance(parsed, dict) and "text" in parsed:
                                btn = parsed.get("buttons", [])
                                if isinstance(btn, dict):
                                    btn = [btn]
                                # Prepend any prose text before the JSON
                                prefix = text[:brace_start].strip()
                                final_text = parsed["text"]
                                if prefix:
                                    final_text = prefix + "\n\n" + final_text
                                return final_text, btn
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break
        return None

    result = _try_parse_json_response(clean_text)
    if result:
        return result[0], full_messages, result[1]

    # Fallback for standard LangGraph response lists
    if isinstance(content, list):
        text_blocks = [block["text"] for block in content if isinstance(block, dict) and "text" in block]
        if text_blocks:
            return "\n".join(text_blocks), full_messages, []
        
    return clean_text, full_messages, []
