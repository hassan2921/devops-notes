#!/bin/bash
# EC2 Launch Template "User data" (Amazon Linux 2023).
# Runs once, as root, when each Auto Scaling instance boots.
# Replace REPO_URL with YOUR GitHub repository.
set -euxo pipefail

REPO_URL="https://github.com/<your-username>/<your-repo>.git"

# 1. Install Docker + git
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

# 2. Install the Docker Compose v2 plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# 3. Get the app and start it
cd /home/ec2-user
git clone "$REPO_URL" app
cd app
cp .env.example .env
docker compose up -d --build

chown -R ec2-user:ec2-user /home/ec2-user/app
