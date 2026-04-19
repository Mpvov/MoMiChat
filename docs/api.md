# MoMiChat API Documentation

MoMiChat exposes a set of REST endpoints for internal service communication and external webhooks.

## Base URL
The default base URL for the API is `http://<host>:<port>/api/v1`.

## Endpoints

### 1. Chat Message Processing (Unified Endpoint)
Used by bot polling nodes to process user messages. This endpoint handles command interception, conversational history, and AI logic in a single call.

- **URL**: `/webhooks/chat/process_message`
- **Method**: `POST`
- **Auth Required**: No (Internal assumed)
- **Request Body**:
  ```json
  {
    "platform": "telegram",
    "user_id": "123456789",
    "text": "Cho con 1 ly trà sữa",
    "username": "customer_nick",
    "display_name": "Customer Name"
  }
  ```
- **Success Response**: `200 OK`
  ```json
  {
    "status": "ok",
    "response_text": "Dạ mẹ nhận đơn cho con rồi nha! Con chọn size nào nè?",
    "buttons": [
      {
        "text": "Size M",
        "callback_data": "size:M"
      },
      {
        "text": "Size L",
        "callback_data": "size:L"
      }
    ]
  }
  ```

#### Features:
- **Command Interception**: If `text` starts with `/` (e.g., `/cart`), it bypasses the AI and returns a deterministic response immediately.
- **Stateful Memory**: Conversation history is automatically retrieved and saved to Redis on every request.
- **Formatting**: Responses are formatted using Telegram-compatible Markdown (single `*` for bold).

### 2. PayOS Webhook
The entry point for PayOS to confirm successful transactions.

- **URL**: `/webhooks/payos`
- **Method**: `POST`
- **Auth Required**: No (Signature verification handled internally)
- **Request Body**: Encrypted/Signed JSON payload from PayOS.
- **Verification**: Automatically verifies the signature using the `PAYOS_CHECKSUM_KEY`.

## System Health

- **URL**: `/health`
- **Method**: `GET`
- **Response**: `{"status": "healthy"}`
