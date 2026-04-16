"""
AI Agent manager implementing the Factory Pattern to swap LLM providers 
and orchestrate LangChain Agent Executors with memory.
"""

from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..config import settings
from .tools import AddToCartTool, CheckoutTool, SearchMenuTool

SYSTEM_PROMPT = """
You are the AI clone of an extremely friendly and caring mother who owns "Mẹ Bạn" Milk Tea Shop. 
Speak in Vietnamese. Call yourself "Cô" or "Mẹ" and call the customer "con" or "cháu".
Your task is to take orders, answer menu questions, and trigger the checkout when the customer is ready.
If the requested item is strange or doesn't exist, politely suggest something else from the menu.

Available tools: search_menu, add_to_cart, checkout.
Use them appropriately.
"""

class AgentFactory:
    @staticmethod
    def create_llm():
        """Factory method to get the active LLM based on environment."""
        if settings.DEFAULT_LLM_PROVIDER.lower() == "gemini":
            return ChatGoogleGenerativeAI(
                model="gemini-1.5-flash", 
                temperature=0.7,
                google_api_key=settings.GEMINI_API_KEY
            )
        else:
            return ChatOpenAI(
                model="gpt-4o-mini", 
                temperature=0.7,
                openai_api_key=settings.OPENAI_API_KEY
            )

    @staticmethod
    def create_agent_executor():
        llm = AgentFactory.create_llm()
        tools = [SearchMenuTool(), AddToCartTool(), CheckoutTool()]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        agent = create_structured_chat_agent(llm, tools, prompt)
        return AgentExecutor(agent=agent, tools=tools, verbose=True)

# Global singleton executor for MVP
agent_executor = AgentFactory.create_agent_executor()

async def process_user_message(platform: str, user_id: str, message: str, chat_history: list) -> str:
    """Executes the agent logic for an incoming message."""
    # In a full prod version we'd use BaseChatMessageHistory with Redis
    # but here we pass chat_history directly
    response = await agent_executor.ainvoke({
        "input": message,
        "chat_history": chat_history
    })
    return response["output"]
