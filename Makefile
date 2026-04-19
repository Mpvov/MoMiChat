.PHONY: install dev dev-ui dev-bot up down infra-up infra-down test lint format clean setup-server install-services status

# --- Local Development ---
install:
	uv sync

dev:
	uv run uvicorn src.momichat.main:app --host 0.0.0.0 --port 8080 --reload

dev-ui:
	uv run streamlit run src/momichat/ui/app.py

dev-bot:
	uv run python bots/telegram/app.py

# --- Production (Manual MVP on EC2) ---

# 1. Setup server dependencies (Ubuntu 24.04)
setup-server:
	sudo apt update && sudo apt install -y curl python3-pip python3-venv python3-full
	# Use official Docker convenience script to avoid dependency conflicts
	curl -fsSL https://get.docker.com -o get-docker.sh
	sudo sh get-docker.sh
	# Add current user to docker group
	sudo usermod -aG docker $${USER}
	# Install uv
	curl -LsSf https://astral.sh/uv/install.sh | sh
	@echo "--- SETUP COMPLETE ---"
	@echo "1. Run 'newgrp docker' or restart your shell to use docker without sudo."
	@echo "2. Run 'source \$$HOME/.cargo/env' to use uv."


# 2. Spin up the Database infrastructure
infra-up:
	docker compose -f deploy/docker-compose.infra.yml up -d

infra-down:
	docker compose -f deploy/docker-compose.infra.yml down

# 3. Install and start application services via Systemd
install-services:
	sudo cp deploy/momichat-*.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable momichat-api momichat-bot momichat-ui
	sudo systemctl restart momichat-api momichat-bot momichat-ui
	@echo "Services installed and started."

stop-services:
	sudo systemctl stop momichat-api momichat-bot momichat-ui
	@echo "Application services stopped."

restart-services:
	sudo systemctl restart momichat-api momichat-bot momichat-ui
	@echo "Application services restarted."

# Check status of everything
status:
	@echo "--- Infrastructure ---"
	docker compose -f deploy/docker-compose.infra.yml ps
	@echo "\n--- Application Services ---"
	systemctl status momichat-api momichat-bot momichat-ui --no-pager -l

status-api:
	journalctl -u momichat-api -f

status-bot:
	journalctl -u momichat-bot -f

status-ui:
	journalctl -u momichat-ui -f

# --- Quality & Maintenance ---
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
