#!/bin/bash
# Hummingbot SaaS Platform - 服务器部署脚本（生产环境）
# 适用于 Ubuntu 22.04 LTS

set -e

echo "======================================"
echo "🚀 Hummingbot SaaS Platform"
echo "   服务器部署脚本（生产环境）"
echo "======================================"
echo ""

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    echo "❌ 请使用 root 权限运行此脚本"
    echo "   sudo bash deploy-server.sh"
    exit 1
fi

# 1. 安装依赖
echo "📦 安装系统依赖..."
apt update
apt install -y \
    git \
    curl \
    wget \
    vim \
    htop \
    ca-certificates \
    gnupg \
    lsb-release

# 2. 安装 Docker
echo ""
echo "🐳 安装 Docker..."
if ! command -v docker &> /dev/null; then
    # 添加 Docker GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # 添加 Docker 仓库
    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    # 安装 Docker
    apt update
    apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # 启动 Docker
    systemctl enable docker
    systemctl start docker

    echo "✓ Docker 安装完成"
else
    echo "✓ Docker 已安装"
fi

# 3. 创建项目目录
echo ""
echo "📁 创建项目目录..."
PROJECT_DIR="/opt/hummingbot-saas"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# 4. 克隆或更新代码（如果是从 Git 部署）
echo ""
read -p "是否从 Git 克隆代码？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "请输入 Git 仓库地址: " GIT_REPO
    if [ -d ".git" ]; then
        echo "📥 更新代码..."
        git pull
    else
        echo "📥 克隆代码..."
        git clone $GIT_REPO .
    fi
fi

# 5. 配置环境变量
echo ""
echo "⚙️  配置环境变量..."
if [ ! -f ".env" ]; then
    cp .env.example .env

    # 生成随机密钥
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    ENCRYPTION_KEY=$(python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

    # 更新 .env
    sed -i "s|your-jwt-secret-key-change-in-production|$JWT_SECRET|g" .env
    sed -i "s|your-encryption-master-key-change-in-production|$ENCRYPTION_KEY|g" .env
    sed -i "s|APP_ENV=development|APP_ENV=production|g" .env
    sed -i "s|DEBUG=true|DEBUG=false|g" .env

    # 添加密码
    echo "" >> .env
    echo "# Generated Passwords" >> .env
    echo "DB_PASSWORD=$DB_PASSWORD" >> .env
    echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> .env

    echo "✓ 环境变量已生成"
    echo ""
    echo "⚠️  请编辑 .env 文件，配置以下项："
    echo "   - BASE_DOMAIN（你的域名）"
    echo "   - ADMIN_EMAIL（管理员邮箱）"
    echo "   - SMTP_*（邮件配置）"
    echo "   - TELEGRAM_BOT_TOKEN（可选）"
    echo ""
    read -p "按 Enter 继续编辑 .env 文件..."
    vim .env
else
    echo "✓ 使用现有 .env 文件"
fi

# 6. 创建必要的目录
echo ""
echo "📁 创建数据目录..."
mkdir -p /srv/tenants
mkdir -p /srv/backups
chmod 755 /srv/tenants
chmod 755 /srv/backups
echo "✓ 目录已创建"

# 7. 构建 Docker 镜像
echo ""
echo "🏗️  构建 Docker 镜像..."
docker compose build
echo "✓ 镜像构建完成"

# 8. 启动服务
echo ""
echo "🚀 启动服务..."
docker compose up -d
echo "✓ 服务已启动"

# 9. 等待数据库启动
echo ""
echo "⏳ 等待数据库启动..."
sleep 10

# 10. 初始化数据库
echo ""
echo "🗄️  初始化数据库..."
docker compose exec portal-api python scripts/init_system.py
echo "✓ 数据库初始化完成"

# 11. 配置防火墙
echo ""
echo "🔥 配置防火墙..."
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp   # SSH
    ufw allow 80/tcp   # HTTP
    ufw allow 443/tcp  # HTTPS
    ufw --force enable
    echo "✓ 防火墙已配置"
else
    echo "⚠️  UFW 未安装，请手动配置防火墙"
fi

# 12. 配置定时任务
echo ""
echo "⏰ 配置定时任务..."
CRON_FILE="/etc/cron.d/hummingbot-saas"
cat > $CRON_FILE <<EOF
# Hummingbot SaaS Platform - 定时任务

# 每天凌晨 2 点备份
0 2 * * * root cd $PROJECT_DIR && docker compose exec -T portal-api python scripts/daily_backup.py >> /var/log/hummingbot-backup.log 2>&1

# 每天凌晨 3 点清理
0 3 * * * root cd $PROJECT_DIR && docker compose exec -T portal-api python scripts/cleanup_backups.py >> /var/log/hummingbot-cleanup.log 2>&1

# 每 5 分钟健康检查
*/5 * * * * root cd $PROJECT_DIR && docker compose exec -T portal-api python scripts/health_check.py >> /var/log/hummingbot-health.log 2>&1
EOF
chmod 644 $CRON_FILE
echo "✓ 定时任务已配置"

# 13. 显示状态
echo ""
echo "======================================"
echo "✅ 部署完成！"
echo "======================================"
echo ""
echo "📊 服务状态："
docker compose ps
echo ""
echo "🌐 访问地址："
BASE_DOMAIN=$(grep BASE_DOMAIN .env | cut -d'=' -f2)
echo "   Portal API: https://api.$BASE_DOMAIN"
echo "   API 文档: https://api.$BASE_DOMAIN/docs"
echo "   Traefik Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "👤 管理员账号："
echo "   邮箱: admin@yourdomain.com"
echo "   密码: changeme123"
echo "   ⚠️  请立即修改密码！"
echo ""
echo "📝 常用命令："
echo "   查看日志: docker compose logs -f"
echo "   重启服务: docker compose restart"
echo "   停止服务: docker compose down"
echo "   查看状态: docker compose ps"
echo ""
echo "🔒 安全提示："
echo "   1. 修改管理员密码"
echo "   2. 配置 SSL 证书（Traefik 自动申请）"
echo "   3. 配置备份策略"
echo "   4. 监控服务器资源"
echo ""
echo "======================================"
