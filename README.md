# MoMiChat: The AI-Powered "Mother's Touch" for Your Shop 🧋

MoMiChat is an advanced AI conversational agent designed to help small merchants automate their online sales without losing the personal touch. Specifically tailored for a milk tea shop, MoMiChat acts as a digital twin of the shop owner ("Mom"), handling everything from product recommendations to automated payment processing via PayOS.

## ✨ Key Features

- **🧠 Persona-Driven AI**: Clones the shop owner's friendly and caring communication style ("Cô" & "Con").
- **🔄 Persistent Conversational Memory**: Remembers past interactions across sessions using a robust Redis-based memory service.
- **⚡ Smart Command Interceptor**: Instant handling of slash commands (`/start`, `/cart`, `/menu`) to save LLM costs and increase reliability.
- **🔘 Interactive Experience**: Supports dynamic buttons and menus for faster decision-making (Size, Toppings, Checkout).
- **🔍 Semantic Menu Search**: Uses vector embeddings (ChromaDB) to understand natural language requests.
- **💳 Fully Integrated Payments**: Seamless PayOS integration for QR payment links and automated status updates.
- **🚀 Cloud Ready**: Automated CI/CD deployment to **AWS EC2** with pre-configured Nginx and SSL support.
- **📊 Shop Manager Dashboard**: Real-time Streamlit dashboard for order fulfillment and business analytics.

## 🏗️ Technical Architecture

See the detailed [Architecture Documentation](docs/architecture.md) for Mermaid diagrams and component breakdowns.

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Docker & Docker Compose
- Redis (Required for memory and shopping carts)
- PayOS API Keys & OpenAI/Gemini API Key

### Installation & Deployment

- **Local Development**: Follow the [Installation Guide](docs/installation.md).
- **Production Deployment**: Follow the [Deployment Guide](docs/deployment.md) for AWS EC2.

### Quick Start (Local Docker)
1. Clone the repo and configure your `.env`.
2. Run `docker-compose up --build`.

## 📂 Project Structure

- `src/momichat`: Main application source code (AI, API, Services).
- `bots/`: Platform-specific bot implementations (Telegram).
- `deploy/`: Production deployment scripts, Nginx config, and Docker Compose overrides.
- `.github/workflows`: CI/CD automation pipelines.
- `docs/`: Detailed technical documentation.

## 📜 License
MIT License. See [LICENSE](LICENSE.md) for more details.
