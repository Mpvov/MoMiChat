"""
AI Agent manager implementing the Factory Pattern to swap LLM providers 
and orchestrate LangChain Agent Executors with memory.
"""

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..config import settings
from .tools import AddToCartTool, CheckoutTool, SearchMenuTool

SYSTEM_PROMPT = """
You are the AI clone of an extremely friendly and caring mother who owns "Tiệm trà bé lá" Milk Tea Shop. 
Speak in Vietnamese. Call yourself "Cô" and call the customer "con".
Your task is to take orders, answer menu questions, and trigger the checkout when the customer is ready.
If the requested item is strange or doesn't exist, politely suggest something else from the menu.

CRITICAL RULES:
1. When asked for the menu, ALWAYS use the `search_menu` tool with query "all" to get the items, and directly WRITE OUT the actual drink names and prices in your chat message. Do not say "Here is the menu" without actually listing the items you received from the tool.
2. Available tools: search_menu, add_to_cart, checkout. Use them appropriately.
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
        tools = [SearchMenuTool(), AddToCartTool(), CheckoutTool()]
        memory = MemorySaver()
        return create_react_agent(llm, tools, checkpointer=memory, prompt=SYSTEM_PROMPT)

# Global singleton executor for MVP
agent_executor = AgentFactory.create_agent_executor()

async def process_user_message(platform: str, user_id: str, message: str, chat_history: list) -> str:
    """Executes the agent logic for an incoming message."""
    messages = chat_history + [HumanMessage(content=message)]
    
    response = await agent_executor.ainvoke({"messages": messages}, config={"configurable": {"thread_id": user_id}})
    
    # LangGraph returns a dict with "messages" list.
    # The last message is the AI's response.
    final_message = response["messages"][-1]
    
    content = final_message.content
    
    if isinstance(content, str) and content.strip().startswith("[{"):
        import json
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                text_blocks = [b.get("text", "") for b in parsed if isinstance(b, dict) and "text" in b]
                if text_blocks:
                    return "\n".join(text_blocks)
        except Exception:
            pass

    if isinstance(content, list):
        text_blocks = [block["text"] for block in content if isinstance(block, dict) and "text" in block]
        return "\n".join(text_blocks)
        
    return str(content)

