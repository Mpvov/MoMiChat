import json
import logging
import redis.asyncio as redis

from langchain_core.messages import messages_from_dict, messages_to_dict
from ..config import settings

logger = logging.getLogger(__name__)

MEMORY_PREFIX = "memory:"
MEMORY_TTL = 60 * 60 * 24  # Keep conversations for 24 hours

def _memory_key(platform: str, user_id: str) -> str:
    return f"{MEMORY_PREFIX}{platform}:{user_id}"

class MemoryService:
    def __init__(self) -> None:
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def get_history(self, platform: str, user_id: str) -> list:
        """Retrieve the user's past messages from Redis."""
        key = _memory_key(platform, user_id)
        data = await self.redis.get(key)
        if data is None:
            return []
        
        # Convert JSON back into LangChain Message objects
        dict_messages = json.loads(data)
        return messages_from_dict(dict_messages)

    async def save_history(self, platform: str, user_id: str, messages: list) -> None:
        """Save the updated LangChain message list to Redis."""
        key = _memory_key(platform, user_id)
        
        # Filter out tool calls to save tokens and prevent strict API errors from broken tool sequences
        filtered_messages = []
        for msg in messages:
            if msg.type == "human":
                filtered_messages.append(msg)
            elif msg.type == "ai" and not getattr(msg, "tool_calls", None):
                filtered_messages.append(msg)
        
        # Limit to the last 10 conversational messages (roughly 5 back-and-forths) 
        # to ensure we don't blow up context limits or Redis size
        trimmed_messages = filtered_messages[-10:]
        
        # Convert LangChain messages to JSON-safe dictionaries
        dict_messages = messages_to_dict(trimmed_messages)
        await self.redis.set(key, json.dumps(dict_messages), ex=MEMORY_TTL)

    async def clear_history(self, platform: str, user_id: str) -> None:
        """Clear the user's conversational history."""
        key = _memory_key(platform, user_id)
        await self.redis.delete(key)
