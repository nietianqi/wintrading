#!/bin/bash
# Hummingbot SaaS Platform - CentOS Stream 自动化部署脚本
# 服务器: 43.161.216.248
# 使用方法: bash <(curl -fsSL https://raw.githubusercontent.com/yourusername/hummingbot-saas/main/deploy-remote.sh)

set -e

echo "======================================"
echo "🚀 Hummingbot SaaS Platform"
echo "   CentOS Stream 自动化部署"
echo "======================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 权限运行此脚本${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Root 权限确认${NC}"

# 步骤 1：更新系统
echo ""
echo "1️⃣  更新系统..."
yum update -y
echo -e "${GREEN}✓ 系统更新完成${NC}"

# 步骤 2：安装基础工具
echo ""
echo "2️⃣  安装基础工具..."
yum install -y \
    git \
    curl \
    wget \
    vim \
    htop \
    net-tools \
    yum-utils \
    device-mapper-persistent-data \
    lvm2

echo -e "${GREEN}✓ 基础工具安装完成${NC}"

# 步骤 3：安装 Docker
echo ""
echo "3️⃣  安装 Docker..."

if command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker 已安装，跳过${NC}"
else
    # 添加 Docker 仓库
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

    # 安装 Docker
    yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # 启动 Docker
    systemctl start docker
    systemctl enable docker

    echo -e "${GREEN}✓ Docker 安装完成${NC}"
fi

docker --version

# 步骤 4：安装 Python 3
echo ""
echo "4️⃣  安装 Python 3..."

if command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python 3 已安装，跳过${NC}"
else
    yum install -y python3 python3-pip
    echo -e "${GREEN}✓ Python 3 安装完成${NC}"
fi

python3 --version

# 步骤 5：配置防火墙
echo ""
echo "5️⃣  配置防火墙..."

# 安装并启动 firewalld
if ! systemctl is-active --quiet firewalld; then
    yum install -y firewalld
    systemctl start firewalld
    systemctl enable firewalld
fi

# 开放必要端口
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --permanent --add-port=8000/tcp  # Portal API
firewall-cmd --permanent --add-port=8080/tcp  # Traefik Dashboard
firewall-cmd --reload

echo -e "${GREEN}✓ 防火墙配置完成${NC}"

# 步骤 6：创建项目目录
echo ""
echo "6️⃣  创建项目目录..."

PROJECT_DIR="/opt/hummingbot-saas"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

echo -e "${GREEN}✓ 项目目录创建完成: $PROJECT_DIR${NC}"

# 步骤 7：克隆代码
echo ""
echo "7️⃣  克隆项目代码..."

if [ -d ".git" ]; then
    echo -e "${YELLOW}代码已存在，更新...${NC}"
    git pull
else
    echo "请输入 Git 仓库地址（或按 Enter 跳过，稍后手动上传代码）："
    read -r GIT_REPO

    if [ -n "$GIT_REPO" ]; then
        git clone $GIT_REPO .
    else
        echo -e "${YELLOW}跳过克隆，请手动上传代码到 $PROJECT_DIR${NC}"
    fi
fi

# 步骤 8：配置环境变量
echo ""
echo "8️⃣  配置环境变量..."

cd $PROJECT_DIR/saas-platform

if [ ! -f ".env" ]; then
    cp .env.example .env

    # 生成密钥
    echo "生成密钥..."
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
    echo "# Auto-generated passwords" >> .env
    echo "DB_PASSWORD=$DB_PASSWORD" >> .env
    echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> .env

    # 配置域名（使用 IP）
    SERVER_IP="43.161.216.248"
    sed -i "s|BASE_DOMAIN=yourdomain.com|BASE_DOMAIN=$SERVER_IP|g" .env
    sed -i "s|ADMIN_EMAIL=admin@yourdomain.com|ADMIN_EMAIL=admin@example.com|g" .env

    echo -e "${GREEN}✓ 环境变量配置完成${NC}"
    echo ""
    echo -e "${YELLOW}生成的密码（请保存）：${NC}"
    echo "数据库密码: $DB_PASSWORD"
    echo "Redis 密码: $REDIS_PASSWORD"
    echo ""
else
    echo -e "${YELLOW}使用现有 .env 文件${NC}"
fi

# 步骤 9：创建数据目录
echo ""
echo "9️⃣  创建数据目录..."

mkdir -p /srv/tenants
mkdir -p /srv/backups

chmod -R 755 /srv/tenants
chmod -R 755 /srv/backups

echo -e "${GREEN}✓ 数据目录创建完成${NC}"

# 步骤 10：创建 Docker 网络
echo ""
echo "🔟 创建 Docker 网络..."

docker network create web 2>/dev/null || echo "网络已存在"

echo -e "${GREEN}✓ Docker 网络创建完成${NC}"

# 步骤 11：启动服务
echo ""
echo "1️⃣1️⃣  启动服务..."

# 使用 docker compose
docker compose up -d

echo -e "${GREEN}✓ 服务启动成功${NC}"

# 等待数据库启动
echo ""
echo "⏳ 等待数据库启动..."
sleep 15

# 步骤 12：初始化数据库
echo ""
echo "1️⃣2️⃣  初始化数据库..."

# 安装 Python 依赖
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# 运行初始化脚本
python3 scripts/init_system.py

echo -e "${GREEN}✓ 数据库初始化完成${NC}"

# 步骤 13：配置定时任务
echo ""
echo "1️⃣3️⃣  配置定时任务..."

CRON_FILE="/etc/cron.d/hummingbot-saas"
cat > $CRON_FILE <<EOF
# Hummingbot SaaS Platform - 定时任务

# 每天凌晨 2 点备份
0 2 * * * root cd $PROJECT_DIR/saas-platform && docker compose exec -T portal-api python scripts/daily_backup.py >> /var/log/hummingbot-backup.log 2>&1

# 每天凌晨 3 点清理
0 3 * * * root cd $PROJECT_DIR/saas-platform && docker compose exec -T portal-api python scripts/cleanup_backups.py >> /var/log/hummingbot-cleanup.log 2>&1

# 每 5 分钟健康检查
*/5 * * * * root cd $PROJECT_DIR/saas-platform && docker compose exec -T portal-api python scripts/health_check.py >> /var/log/hummingbot-health.log 2>&1
EOF

chmod 644 $CRON_FILE

echo -e "${GREEN}✓ 定时任务配置完成${NC}"

# 步骤 14：配置系统服务（开机自启）
echo ""
echo "1️⃣4️⃣  配置系统服务..."

# 创建 systemd 服务
cat > /etc/systemd/system/hummingbot-saas.service <<EOF
[Unit]
Description=Hummingbot SaaS Platform
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR/saas-platform
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# 启用服务
systemctl daemon-reload
systemctl enable hummingbot-saas.service

echo -e "${GREEN}✓ 系统服务配置完成${NC}"

# 完成
echo ""
echo "======================================"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "======================================"
echo ""
echo "📊 服务状态:"
docker compose ps

echo ""
echo "🌐 访问地址:"
echo "  Portal API:    http://43.161.216.248:8000"
echo "  API 文档:      http://43.161.216.248:8000/docs"
echo "  Traefik 仪表盘: http://43.161.216.248:8080"

echo ""
echo "👤 默认管理员账号:"
echo "  邮箱: admin@yourdomain.com"
echo "  密码: changeme123"
echo "  ⚠️  请立即修改密码！"

echo ""
echo "📝 常用命令:"
echo "  查看日志:      docker compose logs -f"
echo "  重启服务:      docker compose restart"
echo "  停止服务:      docker compose down"
echo "  查看状态:      docker compose ps"

echo ""
echo "🔒 安全提示:"
echo "  1. 立即修改管理员密码"
echo "  2. 修改服务器 root 密码: passwd"
echo "  3. 配置域名（可选）"
echo "  4. 配置 SSL 证书（可选）"

echo ""
echo "🧪 测试部署:"
echo "  bash test-deployment.sh"

echo ""
echo "======================================"
