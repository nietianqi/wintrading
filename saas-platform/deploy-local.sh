#!/bin/bash
# Hummingbot SaaS Platform - 一键部署脚本（本地开发环境）
# 用于快速启动测试

set -e

echo "======================================"
echo "🚀 Hummingbot SaaS Platform"
echo "   本地快速部署脚本"
echo "======================================"
echo ""

# 检查依赖
echo "📋 检查依赖..."

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 未安装，请先安装 Python 3.10+"
    exit 1
fi
echo "✓ Python $(python3 --version)"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi
echo "✓ Docker $(docker --version)"

# 检查 PostgreSQL
if ! command -v psql &> /dev/null; then
    echo "⚠️  PostgreSQL 客户端未安装，将使用 Docker 版本"
    USE_DOCKER_DB=true
else
    echo "✓ PostgreSQL 已安装"
    USE_DOCKER_DB=false
fi

echo ""

# 创建 Python 虚拟环境
echo "📦 创建 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ 虚拟环境已创建"
else
    echo "✓ 虚拟环境已存在"
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo ""
echo "📦 安装 Python 依赖..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ 依赖安装完成"

# 创建 .env 文件
echo ""
echo "⚙️  配置环境变量..."
if [ ! -f ".env" ]; then
    cp .env.example .env

    # 生成随机密钥
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    ENCRYPTION_KEY=$(python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

    # 更新 .env
    sed -i.bak "s|your-jwt-secret-key-change-in-production|$JWT_SECRET|g" .env
    sed -i.bak "s|your-encryption-master-key-change-in-production|$ENCRYPTION_KEY|g" .env
    sed -i.bak "s|DATABASE_URL=postgresql://postgres:password@localhost:5432/hummingbot_saas|DATABASE_URL=postgresql://postgres:$DB_PASSWORD@localhost:5432/hummingbot_saas|g" .env

    rm -f .env.bak

    echo "✓ 环境变量已配置（.env 文件已创建）"
else
    echo "✓ 环境变量已存在（使用现有 .env 文件）"
fi

# 启动 PostgreSQL（Docker）
echo ""
if [ "$USE_DOCKER_DB" = true ]; then
    echo "🗄️  启动 PostgreSQL (Docker)..."

    # 停止旧容器
    docker stop hummingbot-saas-db 2>/dev/null || true
    docker rm hummingbot-saas-db 2>/dev/null || true

    # 启动新容器
    docker run -d \
        --name hummingbot-saas-db \
        -e POSTGRES_DB=hummingbot_saas \
        -e POSTGRES_USER=postgres \
        -e POSTGRES_PASSWORD=$(grep DATABASE_URL .env | cut -d':' -f3 | cut -d'@' -f1) \
        -p 5432:5432 \
        postgres:15-alpine

    echo "⏳ 等待 PostgreSQL 启动..."
    sleep 5
    echo "✓ PostgreSQL 已启动"
fi

# 初始化数据库
echo ""
echo "🗄️  初始化数据库..."
python3 scripts/init_system.py

echo ""
echo "======================================"
echo "✅ 部署完成！"
echo "======================================"
echo ""
echo "📝 下一步操作："
echo ""
echo "1. 启动 Portal API："
echo "   source venv/bin/activate"
echo "   python api/main.py"
echo ""
echo "2. 访问 API 文档："
echo "   http://localhost:8000/docs"
echo ""
echo "3. 默认管理员账号："
echo "   邮箱: admin@yourdomain.com"
echo "   密码: changeme123"
echo "   ⚠️  请立即修改密码！"
echo ""
echo "4. 查看日志："
echo "   docker logs -f hummingbot-saas-db"
echo ""
echo "======================================"
