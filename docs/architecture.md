# MoMiChat Architecture

MoMiChat is a modular, AI-first retail platform designed for small merchants. It clones the merchant's persona ("Mom") using Large Language Models to handle complex customer interactions, order processing, and automated payments.

## System Overview

```mermaid
graph TD
    subgraph "Clients"
        TG[Telegram Bot]
        ST[Streamlit Dashboard]
    end

    subgraph "Backend (FastAPI)"
        MA[Main API]
        WEB[Webhooks Endpoint]
        AS[Agent Service]
        CMD[Command Service]
        MEM[Memory Service]
    end

    subgraph "Persistence"
        PG[(PostgreSQL)]
        RD[(Redis)]
        CH[(ChromaDB)]
    end

    subgraph "External Services"
        LLM[OpenAI / Gemini]
        PYOS[PayOS]
    end

    TG <--> AS
    TG <--> CMD
    ST <--> MA
    MA <--> PG
    MA <--> RD
    AS <--> CH
    AS <--> LLM
    AS <--> MEM
    MEM <--> RD
    CMD <--> RD
    WEB <--- PYOS
    MA <--> PYOS
```

## Hybrid Production Infrastructure

MoMiChat utilizes a optimized hybrid model for performance and ease of management.

```mermaid
graph TD
    subgraph "Cloud Host (AWS EC2)"
        subgraph "Docker Resources"
            DB[(PostgreSQL)]
            RD[(Redis)]
            VEC[(ChromaDB)]
        end
        
        subgraph "Systemd Services (Native)"
            API[FastAPI App]
            BOT[Telegram Bot Node]
            UI[Streamlit Dashboard]
        end
        
        NGX[Nginx Proxy] --> API
        NGX --> UI
    end
    
    GH[GitHub] --> |CI/CD| API
```

### Why Hybrid?
- **Infra in Docker**: Database and cache layers are easily versioned and kept isolated.
- **Apps in Systemd**: Application services run natively using `uv run`, allowing for instant restarts, direct host resource access, and simplified logging via `journalctl`.

## Component Breakdown

### 1. AI Agent (`src/momichat/ai`)
- **Knowledge Base**: Semantic menu search via `sentence-transformers`.
- **Agent Logic**: LangGraph orchestration with JSON-structured interactive buttons.

### 2. Services (`src/momichat/services`)
- **Memory Service**: Redis-based session history preservation.
- **Command Service**: High-speed interceptor for slash commands.
- **Payment Service**: PayOS SDK integration for real-time QR generation.

### 3. Adapters (`src/momichat/adapters`)
- **Telegram Adapter**: Handles message delivery, owner notifications, and rich media (including direct QR code images).
