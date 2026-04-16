.PHONY: install dev test lint format clean db-up db-down

install:
	uv sync

dev:
	uv run uvicorn src.momichat.main:app --reload

dev-ui:
	uv run streamlit run src/momichat/ui/app.py

db-up:
	docker-compose up -d

db-down:
	docker-compose down

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
