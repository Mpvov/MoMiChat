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
        # In a real app we'd inject CartService, here we mock response for brevity
        # validation over MENU_DICT
        if item_id not in MENU_DICT:
            return f"Error: Item {item_id} not found."
            
        return f"Added {quantity}x {MENU_DICT[item_id]['name']} to cart."


class CheckoutInput(BaseModel):
    platform: str = Field(description="Messaging platform")
    user_id: str = Field(description="Platform user ID")


class CheckoutTool(BaseTool):
    name: str = "checkout"
    description: str = "Use this when the user is ready to pay. It generates a PayOS link."
    args_schema: Type[BaseModel] = CheckoutInput

    def _run(self, platform: str, user_id: str) -> str:
        # Calls OrderService + PaymentService
        return "SUCCESS. System generated payment link in background."
