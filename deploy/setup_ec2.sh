#!/bin/bash
# EC2 Setup Script for Ubuntu 22.04 LTS / 24.04 LTS
set -e

echo "Updating system..."
sudo apt-get update && sudo apt-get upgrade -y

echo "Installing Docker..."
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add default ubuntu user to docker group
sudo usermod -aG docker ubuntu

echo "Installing Nginx & Certbot..."
sudo apt-get install -y nginx certbot python3-certbot-nginx

echo "Configuring Firewall (UFW)..."
sudo ufw allow "Nginx Full"
sudo ufw allow OpenSSH
sudo ufw --force enable

echo "Setup complete! Please log out and log back in for docker permissions to take effect."
echo "Next step: copy 'deploy/nginx.conf' to '/etc/nginx/sites-available/dreamlite.dev'"
