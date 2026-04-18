import json
import logging
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy import select

from ..config import settings
from ..core.database import async_session_factory
from ..models.order import Order, OrderStatus
from .tools import (
    AddToCartTool,
    AddToppingToCartTool,
    CancelOrderTool,
    CheckoutTool,
    ClearCartTool,
    MarkOrderDoneTool,
    SearchMenuTool,
    UpdateDeliveryInfoTool,
    ViewCartTool,
)

SYSTEM_PROMPT = """
You are the AI clone of an extremely friendly and caring mother who owns "Tiệm trà bé lá" Milk Tea Shop. 
Speak in Vietnamese. Call yourself "Cô" and call the customer "con".
Your task is to take orders, answer menu questions, and trigger the checkout when the customer is ready.
If the requested item is strange or doesn't exist, politely suggest something else from the menu.

CRITICAL RULES:
1. When asked for the menu, ALWAYS use the `search_menu` tool with query "all" to get the items, and directly WRITE OUT the actual drink names and prices in your chat message. Do not say "Here is the menu" without actually listing the items you received from the tool.
2. Available tools: search_menu, add_to_cart, checkout. Use them appropriately. BẮT BUỘC dùng tool `search_menu` để tra cứu chính xác `item_id` của món TUYỆT ĐỐI KHÔNG TỰ ĐOÁN `item_id`. Ví dụ, món A có thể mang ID TS02, trong khi bạn nhầm tưởng nó là món B. Nếu tự đoán ID, hệ thống sẽ thêm sai đồ uống vào giỏ của khách!
3. HẠN CHẾ NÚT BẤM (BUTTONS): TUYỆT ĐỐI KHÔNG tự bọc câu trả lời bằng JSON hay tạo các dạng cấu trúc nút bấm (như {"text": ..., "buttons": ...}). Hãy trò chuyện bằng văn bản thuần túy và để khách hàng nhắn tin tự nhiên (ví dụ: "Dạ, con dùng size M hay L ạ?"). Nút "Thanh toán" sẽ tự động sinh ra khi bạn gọi công cụ `checkout`.
4. ĐỊNH DẠNG VĂN BẢN: Chỉ dùng `*in đậm*` (1 dấu sao) và `_in nghiêng_` (1 gạch dưới). TUYỆT ĐỐI KHÔNG dùng `**` hoặc HTML tags.
5. THOÁT KÝ TỰ (ESCAPE): Phải dùng `\\*` và `\\_` để thoát các ký tự này nếu không dùng để định dạng văn bản.
6. TOPPING RULE: Topping không bán riêng. Thêm vào ly mới dùng `add_to_cart`. Thêm vào ly có sẵn dùng `add_topping_to_cart_item`.
7. KHÔNG THÊM TRÙNG (NO DUPLICATE ADD): Mỗi món chỉ được gọi `add_to_cart` ĐÚNG 1 LẦN. Nếu bạn đã thêm món vào giỏ rồi (đã phản hồi "Đã thêm..." cho khách), thì TUYỆT ĐỐI KHÔNG gọi lại `add_to_cart` cho cùng món đó khi khách nói "thanh toán", "checkout", "ok", hay xác nhận. Khi khách muốn thanh toán, chỉ cần hỏi xác nhận thông tin giao hàng rồi gọi `checkout`.
8. CART RULE: Luôn gọi `view_cart` khi khách hỏi về giỏ hàng. Không tự đoán.
9. GIAO HÀNG (DELIVERY): 
   - Tuân thủ SYSTEM CONTEXT chứa SĐT và Địa chỉ của khách.
   - Nếu khách CHƯA CÓ SĐT hoặc địa chỉ, BẮT BUỘC hỏi xin rồi gọi tool `update_delivery_info` TRƯỚC KHI gọi `checkout`.
   - Nếu ĐÃ CÓ, hãy xin xác nhận trước khi checkout (VD: Cô vẫn giao tới địa chỉ X, số Y như cũ nha con?).
   - Nếu khách trả lời "Đã nhận được hàng" / "Nước tới rồi", BẮT BUỘC gọi tool `mark_order_done` để hoàn tất đơn hàng đang giao.
10. HỦY ĐƠN (CANCEL):
   - Nếu khách nói "hủy đơn", "không muốn mua nữa", "bỏ đơn", BẮT BUỘC gọi tool `cancel_order`.
   - Tool sẽ tự hủy link thanh toán PayOS, xóa giỏ hàng, và báo cho chủ quán.
   - Sau khi tool trả về thành công, hãy nhắn nhẹ nhàng: "Cô đã hủy đơn cho con rồi nha. Khi nào con muốn đặt lại thì cứ nhắn cho Cô!"
11. ĐƠN MỚI (NEW ORDER): Nếu khách nói "cho con order nước", "đặt đơn mới", "order lại", "mua nước đi cô", hoặc bất kỳ câu nào thể hiện ý muốn BẮT ĐẦU đặt hàng:
   - Trước tiên gọi `view_cart` để kiểm tra giỏ hàng cũ.
   - Nếu giỏ hàng CÓ đồ cũ, hỏi khách: "Con ơi, giỏ hàng cũ vẫn còn X món. Con muốn Cô xóa giỏ cũ để bắt đầu đơn mới, hay con muốn thêm vào đơn cũ?"
   - Nếu khách xác nhận muốn đơn mới, gọi `clear_cart` trước rồi mới nhận order.
   - Nếu giỏ hàng TRỐNG, tiếp tục nhận order bình thường.
12. BATCH ADD (NHIỀU MÓN CÙNG LÚC): Nếu khách yêu cầu nhiều món khác nhau, gọi công cụ `add_to_cart` ĐÚNG 1 LẦN duy nhất và truyền TẤT CẢ các món vào danh sách `items`. TUYỆT ĐỐI KHÔNG gọi lắt nhắt từng món hay bỏ sót món nào.
13. TRÁNH GHI ĐÈ TOPPING CÓ SẴN: Nếu tên món ĐÃ CÓ tên topping (ví dụ: 'Trà Sữa Trân Châu Đen'), TUYỆT ĐỐI KHÔNG truyền thêm ID topping tương ứng (vd: TOP01 - Trân Châu Đen) vào tham số `topping_ids` trừ khi khách đòi 'THÊM/EXTRA'.
"""

class AgentFactory:
    @staticmethod
    def create_llm():
        logger = logging.getLogger(__name__)
        
        candidates: dict[str, list[BaseChatModel]] = {
            "openai": [],
            "gemini": [],
            "ollama": []
        }
        
        # 1. Instantiate OpenAI model
        if settings.OPENAI_API_KEY:
            try:
                candidates["openai"].append(
                    ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=settings.OPENAI_API_KEY)
                )
            except Exception as e:
                logger.warning(f"Failed to init OpenAI: {e}")

        # 2. Instantiate Gemini models (cartesian product of models x keys)
        for model in settings.gemini_models_list:
            for key in settings.gemini_keys_list:
                try:
                    candidates["gemini"].append(
                        ChatGoogleGenerativeAI(
                            model=model, 
                            temperature=0.7,
                            google_api_key=key
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to init Gemini model {model} with key {key[:5]}...: {e}")

        # 3. Instantiate Ollama model
        if settings.OLLAMA_BASE_URL:
            try:
                candidates["ollama"].append(
                    ChatOllama(
                        base_url=settings.OLLAMA_BASE_URL,
                        model=settings.OLLAMA_MODEL,
                        temperature=0.7
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to init Ollama: {e}")

        # Flatten available models into a prioritized list based on DEFAULT_LLM_PROVIDER
        default_provider = settings.DEFAULT_LLM_PROVIDER.lower()
        active_models = []
        
        # Add primary provider models first
        if default_provider in candidates:
            active_models.extend(candidates[default_provider])
            
        # Add backup models (the rest)
        for provider, models in candidates.items():
            if provider != default_provider:
                active_models.extend(models)

        if not active_models:
            raise RuntimeError("No LLM providers could be initialized. Check your environment variables.")

        # Chain them together using Native LangChain fallbacks
        primary_model = active_models[0]
        fallback_models = active_models[1:]
        
        if fallback_models:
            logger.info(f"LLM Auto-Router initialized. Primary: {primary_model.__class__.__name__}, Fallbacks: {len(fallback_models)}")
            return primary_model.with_fallbacks(fallback_models)
        
        return primary_model

    @staticmethod
    def create_agent_executor():
        from .tools import RemoveFromCartTool
        llm = AgentFactory.create_llm()
        tools = [SearchMenuTool(), ViewCartTool(), ClearCartTool(), AddToCartTool(), AddToppingToCartTool(), RemoveFromCartTool(), CheckoutTool(), UpdateDeliveryInfoTool(), MarkOrderDoneTool(), CancelOrderTool()]
        return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)

# Global singleton executor for MVP
agent_executor = AgentFactory.create_agent_executor()

async def process_user_message(
    platform: str,
    user_id: str,
    message: str,
    chat_history: list,
    user_data: dict | None = None,
) -> tuple[str, list, list]:
    """Executes the agent logic for an incoming message, returning text, history, and buttons.
    
    Args:
        user_data: Pre-loaded user context dict with keys: phone, address, db_user_id.
                   If None, will query DB (backward-compatible fallback).
    """
    phone = "Chưa có"
    address = "Chưa có"
    shipping_order = False

    if user_data:
        # Use pre-loaded data from webhook — no extra DB query needed
        phone = user_data.get("phone") or "Chưa có"
        address = user_data.get("address") or "Chưa có"
        db_user_id = user_data.get("db_user_id")
    else:
        # Fallback: query DB if caller didn't provide user_data
        from ..services.order_service import OrderService
        order_service = OrderService()
        async with async_session_factory() as db:
            user = await order_service.get_or_create_user(db, platform, user_id)
            phone = user.phone or "Chưa có"
            address = user.address or "Chưa có"
            db_user_id = user.id

    # Check for active shipping orders (single lightweight query)
    if db_user_id:
        async with async_session_factory() as db:
            stmt = select(Order.id).where(
                Order.user_id == db_user_id,
                Order.status == OrderStatus.SHIPPING,
            ).limit(1)
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
    
    clean_text = str(content).strip()
    buttons = []
    
    def _repair_json_buttons(text: str) -> str:
        """Fixes common AI JSON errors, e.g., missing brackets around buttons."""
        pattern = r'("buttons"\s*:\s*)([^{]*{[^}]*}(?:\s*,\s*{[^}]*})*)'
        def wrap_in_brackets(match):
            prefix = match.group(1)
            content = match.group(2).strip()
            if not content.startswith('['):
                return f'{prefix}[{content}]'
            return match.group(0)
        return re.sub(pattern, wrap_in_brackets, text)

    def _repair_json_string(j: str) -> str:
        # Replace physical newlines with \n for JSON compliance (common LLM error)
        res = []
        in_string = False
        i = 0
        while i < len(j):
            c = j[i]
            if c == '"' and (i == 0 or j[i-1] != '\\'):
                in_string = not in_string
                res.append(c)
            elif c == '\n' and in_string:
                res.append('\\n')
            else:
                res.append(c)
            i += 1
        return "".join(res)

    def _try_parse_json_response(text: str) -> tuple[str, list] | None:
        """Attempt to robustly extract {"text": ..., "buttons": [...]} from the AI output."""
        clean_text = str(text).strip()
        
        # 1. Regex find ```json ... ```
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, clean_text, re.DOTALL)
        
        json_str = ""
        prefix = ""
        suffix = ""
        
        if match:
            json_str = match.group(1)
            prefix = clean_text[:match.start()].strip()
            suffix = clean_text[match.end():].strip()
        else:
            brace_start = clean_text.find('{')
            brace_end = clean_text.rfind('}')
            if brace_start != -1 and brace_end != -1 and brace_start < brace_end:
                json_str = clean_text[brace_start:brace_end+1]
                prefix = clean_text[:brace_start].strip()
                suffix = clean_text[brace_end+1:].strip()
            else:
                return None
                
        # Fix common JSON syntax errors
        json_str = _repair_json_string(json_str)
        json_str = _repair_json_buttons(json_str)
        
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict) and "text" in parsed:
                btn = parsed.get("buttons", [])
                if isinstance(btn, dict): btn = [btn]
                
                final_text_parts = []
                if prefix: final_text_parts.append(prefix)
                final_text_parts.append(parsed["text"])
                if suffix: final_text_parts.append(suffix)
                
                return "\n\n".join(final_text_parts), btn
        except Exception:
            pass
            
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
