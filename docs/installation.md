# Installation & Configuration Guide

This guide provides detailed steps to set up and run the MoMiChat system.

## Environment Configuration

Create a `.env` file in the root directory based on `.env.example`.

### Required Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection string (Mandatory for Carts & Memory) | `redis://...` |
| `OPENAI_API_KEY` | Key for GPT models | OpenAI Dashboard |
| `GEMINI_API_KEY` | Key for Google AI (Optional if using OpenAI) | Google AI Studio |
| `TELEGRAM_BOT_TOKEN` | Token for your bot | @BotFather |
| `PAYOS_CLIENT_ID` | Client ID | PayOS Dashboard |
| `PAYOS_API_KEY` | API Key | PayOS Dashboard |
| `PAYOS_CHECKSUM_KEY`| Checksum Key | PayOS Dashboard |

## System Components

- **PostgreSQL**: Stores persistent data like Orders and User profiles.
- **Redis**: Acts as a stateful store for **Shopping Carts** and **Conversational Memory**.
- **ChromaDB**: Vector database for searching the menu via semantic similarity.

## Docker Deployment (Local Development)

The easiest way to run the full stack (API, Bot, UI, DB, Redis) is using Docker Compose.

```bash
docker-compose up --build
```

### What happens inside Docker:
1. **db**: Initializes PostgreSQL and wait for readiness.
2. **redis**: Starts the cache layer for memory management.
3. **api**: Starts the FastAPI backend, initializes the ChromaDB menu index, and runs migrations.
4. **bot**: Connects to Telegram and begins long-polling or webhook listening.
5. **ui**: Launches the Streamlit dashboard on port 8501.

## Production Deployment

For deploying to AWS EC2 with CI/CD and SSL support, please refer to the dedicated **[Production Deployment Guide](deployment.md)**.

## Manual Setup (for Developers)

### 1. Installation
```bash
pip install uv
uv sync
```

### 2. Running Services
You can run services individually using the `Makefile`:
- `make run-api`: Starts the FastAPI server.
- `make run-bot`: Starts the Telegram bot node.
- `make run-ui`: Starts the Streamlit dashboard.
