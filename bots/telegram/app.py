import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import httpx
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FASTAPI_INTERNAL_URL = os.getenv("FASTAPI_INTERNAL_URL", "http://localhost:8080/api/v1/webhooks/chat/process_message")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable")

async def forward_to_backend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming standard text messages."""
    message = update.message
    if not message or not message.text:
        return

    user = message.from_user
    chat_id = message.chat_id

    # 1. Prompt native "Typing..." indicator immediately for UX
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    # 2. Prepare standardized payload
    display_name = f"{user.first_name} {user.last_name or ''}".strip()
    payload = {
        "platform": "telegram",
        "user_id": str(user.id),
        "username": user.username,
        "display_name": display_name,
        "text": message.text
    }

    # 3. Call Core FastAPI Backend
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(FASTAPI_INTERNAL_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # 4. Reply with backend's text
            response_text = data.get("response_text", "Sorry, I received an unhandled empty response.")
            await context.bot.send_message(chat_id=chat_id, text=response_text)
            
    except httpx.RequestError as e:
        logger.error(f"HTTP Request failed connecting to FastApi Core: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Hệ thống đang bảo trì, vui lòng thử lại sau nhé con!"
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Hệ thống tạm thời gặp trục trặc xíu, con chờ chút nhé!"
        )

def main():
    logger.info("Initializing Standalone Telegram Bot Node...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Generic message handler that listens to text
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), forward_to_backend)
    application.add_handler(message_handler)

    logger.info("Starting long polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
