# Production Deployment Guide

This guide covers the process of deploying MoMiChat to a production environment on **AWS EC2** using GitHub Actions for CI/CD.

## 1. Initial Server Provisioning

Use the provided setup script to prepare an Ubuntu server (22.04 or 24.04 LTS).

```bash
# On your EC2 Instance
chmod +x deploy/setup_ec2.sh
./deploy/setup_ec2.sh
```

**The script installs:**
- Docker & Docker Compose
- Nginx & Certbot (for SSL)
- Firewall (UFW) configuration (80, 443, 22)

## 2. GitHub Actions Setup

Automated deployment is triggered on every push to the `main` branch.

### Required GitHub Secrets
Navigate to **Settings -> Secrets and variables -> Actions** and add:

| Secret | Description |
|--------|-------------|
| `EC2_HOST` | The Public IPv4 or DNS of your EC2 instance. |
| `EC2_SSH_KEY` | The private SSH key (`.pem`) used to connect to the instance. |

## 3. SSL Configuration (HTTPS)

Once Nginx is installed, obtain an SSL certificate using Certbot:

```bash
sudo certbot --nginx -d yourdomain.com
```

Then, copy the production Nginx configuration:
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/momichat
sudo ln -s /etc/nginx/sites-available/momichat /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 4. Production Runner

The production environment uses `deploy/docker-compose.prod.yml`, which includes:
- **api**: Backend FastAPI service.
- **bot**: Telegram polling node.
- **ui**: Streamlit dashboard.
- **db**: Persistent PostgreSQL.
- **redis**: Cache for memory and carts.

### Manual Troubleshooting
If you need to manually restart or view logs on the server:
```bash
cd /home/ubuntu/MoMiChat
docker compose -f deploy/docker-compose.prod.yml logs -f
```

## 5. Security Best Practices
- Ensure your `.env` file on the server contains production-strength secrets.
- Use `OWNER_CHAT_ID` to restrict admin notifications to yourself.
- Keep the `UFW` firewall enabled and only allow necessary ports.
