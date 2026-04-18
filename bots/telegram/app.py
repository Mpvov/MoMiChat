import logging
import os

import httpx
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FASTAPI_INTERNAL_URL = os.getenv("FASTAPI_INTERNAL_URL", "http://127.0.0.1:8080/api/v1/webhooks/chat/process_message")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable")

async def _send_to_backend(chat_id: int, payload: dict, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(FASTAPI_INTERNAL_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            
            response_text = data.get("response_text", "Sorry, I received an unhandled empty response.")
            buttons = data.get("buttons", [])
            
            reply_markup = None
            if buttons:
                keyboard = []
                for btn in buttons:
                    text = btn.get("text", "Option")
                    callback_data = btn.get("callback_data", "none")
                    keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
                reply_markup = InlineKeyboardMarkup(keyboard)

            # Try sending with Markdown formatting; fall back to plain text if
            # the AI produced broken markdown (unmatched * or _ etc.)
            try:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=response_text, 
                    reply_markup=reply_markup,
                    parse_mode=constants.ParseMode.MARKDOWN
                )
            except Exception as fmt_err:
                logger.warning(f"Markdown parse failed, falling back to plain text: {fmt_err}")
                # Strip markdown characters so the user still sees the message
                plain_text = response_text.replace("*", "").replace("_", "").replace("`", "")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=plain_text,
                    reply_markup=reply_markup
                )
            
    except httpx.RequestError as e:
        logger.error(f"HTTP Request failed connecting to FastApi Core: {type(e).__name__} - {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Hệ thống đang bảo trì, vui lòng thử lại sau nhé con! (Network Error)"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP Status Error from FastApi Core: {e.response.status_code} - {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Hệ thống đang bảo trì, vui lòng thử lại sau nhé con! (Server Error)"
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred: {repr(e)}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Hệ thống tạm thời gặp trục trặc xíu, con chờ chút nhé!"
        )

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

    await _send_to_backend(chat_id, payload, context)

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks from Inline Keyboards."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    text = query.data

    try:
        # Hide the buttons on the message they just clicked to prevent submitting again
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
        
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    display_name = f"{user.first_name} {user.last_name or ''}".strip()
    payload = {
        "platform": "telegram",
        "user_id": str(user.id),
        "username": user.username,
        "display_name": display_name,
        "text": text
    }

    await _send_to_backend(chat_id, payload, context)

def main():
    logger.info("Initializing Standalone Telegram Bot Node...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Generic message handler that listens to text and commands
    message_handler = MessageHandler(filters.TEXT | filters.COMMAND, forward_to_backend)
    application.add_handler(message_handler)

    # Register callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(handle_button_callback))

    logger.info("Starting long polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
