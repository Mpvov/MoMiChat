import asyncio
import logging
import os
import random

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

# ─── Thinking Loop Constants ────────────────────────────────────────────────

THINKING_INTERVAL_SECONDS = 2

THINKING_MESSAGES = [
    "Cô đang xin tín hiệu từ vũ trụ... 🪐",
    "Đang combat với wifi xíu nha... 🥊",
    "Đợi cô xíu, tự nhiên quên ngang... 🤡",
    "Hệ thống đang overthinking... 🤔",
    "Não cô đang load 99% rồi... ⏳",
    "Đang ngồi niệm thần chú chốt đơn... 🧘‍♀️",
    "Ủa khoan... để cô suy nghĩ lại nhân sinh quan... 🍃",
    "Đang load... tự nhiên thấy hơi chằm zn... 🥀",
    "Cô đang nhặt nốt mấy cọng nơ-ron thần kinh... 🧠",
    "Ét ô ét, rớt mạng hay rớt miếng vibe ta... 🛜",
]

ERROR_MESSAGES = [
    "Chết dở, não cô đình công rồi, con F5 nhắn lại nha! 🏳️",
    "Cảm lạnh ghê, mạng mẽo rớt cái độp. Lại từ đầu giúp cô dới! 🥶",
    "Quán đông quá cô lú luôn, con gõ lại câu khác cho cô với nha! 😵‍💫",
    "Trầm cảm ngang, hệ thống báo lỗi rùi. Thử lại xíu nhen! 🥀",
    "Ủa alo? Vũ trụ ngắt kết nối rùi, con nhắn lại thử coi sao! 📡",
    "Lag lòi ke luôn rùi 😭 Bấm gửi lại nha con iu! 💔",
    "Hệ thống đang bất ổn như tâm lý cô vậy... Thử lại nha! 📉",
]


# ─── Core: Backend call + Thinking Loop ─────────────────────────────────────

async def _call_backend(payload: dict) -> dict:
    """Fire the HTTP request to the FastAPI backend and return the JSON response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(FASTAPI_INTERNAL_URL, json=payload)
        response.raise_for_status()
        return response.json()


def _build_reply_markup(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    """Convert a list of button dicts into a Telegram InlineKeyboardMarkup."""
    if not buttons:
        return None
    keyboard = []
    for btn in buttons:
        text = btn.get("text", "Option")
        callback_data = btn.get("callback_data", "none")
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)


async def _send_final_reply(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    response_text: str,
    reply_markup: InlineKeyboardMarkup | None,
):
    """Edit the thinking message with the final AI response."""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=response_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    except Exception as fmt_err:
        logger.warning(f"Markdown parse failed on edit, falling back to plain text: {fmt_err}")
        plain_text = response_text.replace("*", "").replace("_", "").replace("`", "")
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=plain_text,
                reply_markup=reply_markup,
            )
        except Exception as edit_err:
            # If edit also fails (e.g. message too old), send a new message instead
            logger.error(f"Edit fallback also failed: {edit_err}. Sending new message.")
            await context.bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                reply_markup=reply_markup,
            )


async def _process_with_thinking_loop(
    chat_id: int,
    payload: dict,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    The main UX loop:
    1. Send an instant 'thinking' message.
    2. Fire backend call as a background task.
    3. Every 2s, edit the message with a new funny quote.
    4. When backend responds, edit with the real answer.
    5. On error, show a funny error message.
    """
    # 1. Pick a shuffled list of thinking messages (no repeats until exhausted)
    shuffled_thinking = random.sample(THINKING_MESSAGES, len(THINKING_MESSAGES))
    think_idx = 0

    # 2. Send the first thinking message immediately
    sent_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=shuffled_thinking[think_idx],
    )
    message_id = sent_msg.message_id
    think_idx += 1

    # 3. Launch backend call in background
    backend_task = asyncio.create_task(_call_backend(payload))

    # 4. Thinking loop — runs until backend responds (httpx 120s timeout is the safety net)
    while not backend_task.done():
        # Wait for the interval (or until the task finishes, whichever comes first)
        try:
            await asyncio.wait_for(
                asyncio.shield(backend_task),
                timeout=THINKING_INTERVAL_SECONDS,
            )
            # If we get here, the task finished during the wait
            break
        except asyncio.TimeoutError:
            # Task still running, edit with next thinking message
            next_msg = shuffled_thinking[think_idx % len(shuffled_thinking)]
            think_idx += 1
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=next_msg,
                )
            except Exception as e:
                logger.warning(f"Failed to edit thinking message: {e}")
        except (asyncio.CancelledError, Exception):
            break

    # 5. Process the result
    try:
        data = backend_task.result()
        response_text = data.get("response_text", "Xin lỗi, cô không hiểu con nói gì.")
        buttons = data.get("buttons", [])
        reply_markup = _build_reply_markup(buttons)

        await _send_final_reply(context, chat_id, message_id, response_text, reply_markup)

    except httpx.RequestError as e:
        logger.error(f"HTTP Request failed: {type(e).__name__} - {e}")
        error_msg = random.choice(ERROR_MESSAGES)
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP Status Error: {e.response.status_code} - {e}")
        error_msg = random.choice(ERROR_MESSAGES)
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
    except Exception as e:
        logger.error(f"Unexpected error in thinking loop: {repr(e)}")
        error_msg = random.choice(ERROR_MESSAGES)
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)


# ─── Telegram Handlers ──────────────────────────────────────────────────────

async def forward_to_backend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming standard text messages."""
    message = update.message
    if not message or not message.text:
        return

    user = message.from_user
    chat_id = message.chat_id

    # Prepare standardized payload
    display_name = f"{user.first_name} {user.last_name or ''}".strip()
    payload = {
        "platform": "telegram",
        "user_id": str(user.id),
        "username": user.username,
        "display_name": display_name,
        "text": message.text
    }

    await _process_with_thinking_loop(chat_id, payload, context)


async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks from Inline Keyboards."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    text = query.data

    try:
        # Hide the buttons on the message they just clicked to prevent double-click
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    display_name = f"{user.first_name} {user.last_name or ''}".strip()
    payload = {
        "platform": "telegram",
        "user_id": str(user.id),
        "username": user.username,
        "display_name": display_name,
        "text": text
    }

    await _process_with_thinking_loop(chat_id, payload, context)


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
