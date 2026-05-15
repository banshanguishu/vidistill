#!/bin/bash
# 检查参数
APP=${1:-vidistill}
VERSION=${2:-latest}

echo "Deploy $APP Using version: $VERSION"

# 拉取最新镜像
echo "Pulling image version: $VERSION..."
docker pull 192.168.1.252:15000/$APP:$VERSION

mkdir -p ./logs

echo "Deploying with docker-compose..."
docker-compose pull
docker-compose down || true
docker-compose up -d --force-recreate

# 清理旧镜像
echo "Cleaning up old images..."
docker image prune -f

echo "Deployment completed successfully!"
