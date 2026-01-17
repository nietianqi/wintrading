#!/bin/bash
# Hummingbot SaaS Platform - 完整运行脚本
# 包含真实的 Hummingbot 集成

set -e

echo "======================================"
echo "🚀 Hummingbot SaaS Platform"
echo "   完整系统启动"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查是否为 root（生产环境）
if [ "$EUID" -eq 0 ]; then
    IS_PRODUCTION=true
    echo -e "${YELLOW}⚠️  检测到 root 权限，将以生产模式运行${NC}"
else
    IS_PRODUCTION=false
    echo "ℹ️  以开发模式运行"
fi

# 步骤 1：检查依赖
echo ""
echo "1️⃣  检查系统依赖..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    echo "请运行: curl -fsSL https://get.docker.com | sh"
    exit 1
fi
echo "✓ Docker $(docker --version | cut -d' ' -f3)"

if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose 未安装"
    exit 1
fi
echo "✓ Docker Compose $(docker compose version --short)"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 未安装"
    exit 1
fi
echo "✓ Python $(python3 --version | cut -d' ' -f2)"

# 步骤 2：配置环境变量
echo ""
echo "2️⃣  配置环境变量..."

if [ ! -f ".env" ]; then
    echo "创建 .env 文件..."
    cp .env.example .env

    # 生成密钥
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    ENCRYPTION_KEY=$(python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

    # 更新 .env
    sed -i.bak "s|your-jwt-secret-key-change-in-production|$JWT_SECRET|g" .env
    sed -i.bak "s|your-encryption-master-key-change-in-production|$ENCRYPTION_KEY|g" .env

    # 添加密码
    echo "" >> .env
    echo "# Auto-generated passwords" >> .env
    echo "DB_PASSWORD=$DB_PASSWORD" >> .env
    echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> .env

    rm -f .env.bak

    echo "✓ 环境变量已生成"
else
    echo "✓ 使用现有 .env 文件"
fi

# 步骤 3：创建必要的目录
echo ""
echo "3️⃣  创建数据目录..."

mkdir -p /srv/tenants
mkdir -p /srv/backups
mkdir -p ./data/postgres
mkdir -p ./data/redis

if [ "$IS_PRODUCTION" = true ]; then
    chown -R 1000:1000 /srv/tenants /srv/backups
fi

echo "✓ 目录已创建"

# 步骤 4：启动基础设施
echo ""
echo "4️⃣  启动基础设施（数据库、Redis）..."

docker compose up -d postgres redis

echo "⏳ 等待数据库启动..."
sleep 10

# 检查数据库连接
DB_PASSWORD=$(grep DB_PASSWORD .env | cut -d'=' -f2)
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker compose exec postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "✓ 数据库已就绪"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  等待数据库... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ 数据库启动超时"
    exit 1
fi

# 步骤 5：初始化数据库
echo ""
echo "5️⃣  初始化数据库..."

if [ -d "venv" ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt
fi

python3 scripts/init_system.py

echo "✓ 数据库初始化完成"

# 步骤 6：启动 Portal API
echo ""
echo "6️⃣  启动 Portal API..."

docker compose up -d portal-api

echo "⏳ 等待 Portal API 启动..."
sleep 5

# 检查 API 健康
MAX_RETRIES=20
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Portal API 已就绪"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  等待 API... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 3
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "⚠️  API 启动超时，请检查日志: docker compose logs portal-api"
fi

# 步骤 7：启动 Traefik（反向代理）
echo ""
echo "7️⃣  启动 Traefik（反向代理 + 自动 HTTPS）..."

# 创建 acme.json
if [ ! -f "acme.json" ]; then
    touch acme.json
    chmod 600 acme.json
fi

# 创建 Traefik 网络
docker network create web 2>/dev/null || true

docker compose up -d traefik

echo "✓ Traefik 已启动"

# 步骤 8：创建测试租户（演示）
echo ""
echo "8️⃣  创建测试租户（演示 Hummingbot 集成）..."

read -p "是否创建测试租户？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "创建测试用户..."

    # 注册测试用户
    REGISTER_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/register \
      -H "Content-Type: application/json" \
      -d '{
        "email": "demo@test.com",
        "username": "demo",
        "password": "password123",
        "full_name": "Demo User"
      }')

    if echo "$REGISTER_RESPONSE" | grep -q "id"; then
        echo "✓ 测试用户已创建"

        # 登录获取 Token
        LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
          -H "Content-Type: application/json" \
          -d '{
            "email": "demo@test.com",
            "password": "password123"
          }')

        ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

        if [ -n "$ACCESS_TOKEN" ]; then
            echo "✓ 已登录"

            # 创建租户
            echo "创建租户（这将启动完整的 Hummingbot 栈）..."

            TENANT_RESPONSE=$(curl -s -X POST http://localhost:8000/tenants/provision \
              -H "Authorization: Bearer $ACCESS_TOKEN")

            if echo "$TENANT_RESPONSE" | grep -q "id"; then
                TENANT_CODE=$(echo "$TENANT_RESPONSE" | grep -o '"tenant_code":"[^"]*' | cut -d'"' -f4)
                SUBDOMAIN=$(echo "$TENANT_RESPONSE" | grep -o '"subdomain":"[^"]*' | cut -d'"' -f4)

                echo "✓ 租户已创建"
                echo "  租户代码: $TENANT_CODE"
                echo "  Dashboard: http://$SUBDOMAIN"
                echo ""
                echo "  租户栈状态:"
                docker ps --filter "name=$TENANT_CODE"
            else
                echo "⚠️  租户创建失败: $TENANT_RESPONSE"
            fi
        fi
    else
        echo "⚠️  用户创建失败: $REGISTER_RESPONSE"
    fi
fi

# 步骤 9：显示系统状态
echo ""
echo "======================================"
echo "✅ 系统启动完成！"
echo "======================================"
echo ""
echo "📊 服务状态:"
docker compose ps

echo ""
echo "🌐 访问地址:"
echo "  Portal API:    http://localhost:8000"
echo "  API 文档:      http://localhost:8000/docs"
echo "  Traefik 仪表盘: http://localhost:8080"

echo ""
echo "👤 默认管理员账号:"
echo "  邮箱: admin@yourdomain.com"
echo "  密码: changeme123"
echo "  ⚠️  请立即修改密码！"

echo ""
echo "🧪 测试部署:"
echo "  bash test-deployment.sh"

echo ""
echo "📝 常用命令:"
echo "  查看日志:      docker compose logs -f"
echo "  重启服务:      docker compose restart"
echo "  停止系统:      docker compose down"
echo "  查看租户:      docker ps | grep -E 'u[0-9]+-'"

echo ""
echo "📚 文档:"
echo "  快速开始:      QUICKSTART.md"
echo "  生产架构:      docs/PRODUCTION_ARCHITECTURE.md"
echo "  Hummingbot 集成: docs/HUMMINGBOT_INTEGRATION.md"

echo ""
echo "======================================"
echo "🎉 祝你使用愉快！"
echo "======================================"
