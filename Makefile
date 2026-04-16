.PHONY: install dev dev-ui dev-bot up down infra-up infra-down test lint format clean

install:
	uv sync

dev:
	uv run uvicorn src.momichat.main:app --host 0.0.0.0 --port 8080 --reload

dev-ui:
	uv run streamlit run src/momichat/ui/app.py

dev-bot:
	uv run python bots/telegram/app.py

# Spins up the ENTIRE production stack (Databases + API + Bot)
up:
	docker-compose up -d

# Spins down the ENTIRE stack
down:
	docker-compose down

# Use this to spin up JUST the databases/redis for local development
infra-up:
	docker-compose up -d db redis chromadb

infra-down:
	docker-compose stop db redis chromadb

test:
	uv run pytest -v

lint:
	uv run ruff check .

format:
	uv run ruff format .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache
