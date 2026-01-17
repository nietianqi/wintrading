#!/bin/bash
# 部署测试脚本 - 快速验证系统是否正常运行

set -e

echo "======================================"
echo "🧪 Hummingbot SaaS 部署测试"
echo "======================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# API 地址
API_URL="${API_URL:-http://localhost:8000}"

# 测试计数
PASS=0
FAIL=0

# 测试函数
test_api() {
    local endpoint=$1
    local expected_code=$2
    local description=$3

    echo -n "测试: $description ... "

    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL$endpoint")

    if [ "$response" = "$expected_code" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $response)"
        ((PASS++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (Expected $expected_code, got $response)"
        ((FAIL++))
        return 1
    fi
}

# 开始测试
echo "🔍 开始测试..."
echo ""

# 1. 健康检查
echo "1️⃣ 基础健康检查"
test_api "/health" "200" "健康检查接口"
test_api "/" "200" "根路径"
test_api "/docs" "200" "API 文档"
echo ""

# 2. 认证接口
echo "2️⃣ 认证接口"
test_api "/auth/register" "422" "注册接口（需要参数）"
test_api "/auth/login" "422" "登录接口（需要参数）"
echo ""

# 3. 受保护的接口（应该返回 401）
echo "3️⃣ 受保护的接口"
test_api "/users/me" "401" "获取当前用户（未认证）"
test_api "/subscriptions/me" "401" "获取订阅信息（未认证）"
test_api "/bots" "401" "获取 Bot 列表（未认证）"
echo ""

# 4. 创建测试用户
echo "4️⃣ 完整流程测试"
echo -n "创建测试用户 ... "

# 生成随机用户名
RANDOM_USER="test_$(date +%s)"
RANDOM_EMAIL="${RANDOM_USER}@test.com"

# 注册
REGISTER_RESPONSE=$(curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$RANDOM_EMAIL\",
    \"username\": \"$RANDOM_USER\",
    \"password\": \"password123\",
    \"full_name\": \"Test User\"
  }")

if echo "$REGISTER_RESPONSE" | grep -q "id"; then
    echo -e "${GREEN}✓ PASS${NC}"
    ((PASS++))

    # 提取用户 ID
    USER_ID=$(echo "$REGISTER_RESPONSE" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
    echo "  用户 ID: $USER_ID"
else
    echo -e "${RED}✗ FAIL${NC}"
    ((FAIL++))
    echo "  响应: $REGISTER_RESPONSE"
fi

# 5. 登录
echo -n "用户登录 ... "

LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$RANDOM_EMAIL\",
    \"password\": \"password123\"
  }")

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
    echo -e "${GREEN}✓ PASS${NC}"
    ((PASS++))

    # 提取 Token
    ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
    echo "  Token: ${ACCESS_TOKEN:0:20}..."
else
    echo -e "${RED}✗ FAIL${NC}"
    ((FAIL++))
    echo "  响应: $LOGIN_RESPONSE"
fi

# 6. 获取当前用户信息
if [ -n "$ACCESS_TOKEN" ]; then
    echo -n "获取用户信息 ... "

    USER_INFO=$(curl -s -X GET "$API_URL/users/me" \
      -H "Authorization: Bearer $ACCESS_TOKEN")

    if echo "$USER_INFO" | grep -q "$RANDOM_EMAIL"; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAIL++))
    fi

    # 7. 获取订阅信息
    echo -n "获取订阅信息 ... "

    SUBSCRIPTION=$(curl -s -X GET "$API_URL/subscriptions/me" \
      -H "Authorization: Bearer $ACCESS_TOKEN")

    if echo "$SUBSCRIPTION" | grep -q "tier"; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASS++))

        # 提取套餐信息
        TIER=$(echo "$SUBSCRIPTION" | grep -o '"tier":"[^"]*' | cut -d'"' -f4)
        MAX_BOTS=$(echo "$SUBSCRIPTION" | grep -o '"max_bots":[0-9]*' | cut -d':' -f2)
        echo "  套餐: $TIER"
        echo "  最大 Bot 数: $MAX_BOTS"
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAIL++))
    fi
fi

echo ""

# 8. 数据库连接测试
echo "5️⃣ 数据库连接测试"
echo -n "检查数据库容器 ... "

if docker ps | grep -q "hummingbot-saas-db\|hummingbot-portal-db"; then
    echo -e "${GREEN}✓ PASS${NC}"
    ((PASS++))

    # 测试数据库连接
    echo -n "测试数据库连接 ... "

    DB_CONTAINER=$(docker ps --filter "name=postgres" --format "{{.Names}}" | head -1)

    if [ -n "$DB_CONTAINER" ]; then
        DB_TEST=$(docker exec $DB_CONTAINER psql -U postgres -d hummingbot_saas -c "SELECT 1" 2>&1)

        if echo "$DB_TEST" | grep -q "1 row"; then
            echo -e "${GREEN}✓ PASS${NC}"
            ((PASS++))
        else
            echo -e "${RED}✗ FAIL${NC}"
            ((FAIL++))
        fi
    else
        echo -e "${YELLOW}⚠ SKIP${NC} (数据库容器未找到)"
    fi
else
    echo -e "${YELLOW}⚠ SKIP${NC} (数据库容器未运行)"
fi

echo ""

# 测试总结
echo "======================================"
echo "📊 测试总结"
echo "======================================"
echo -e "通过: ${GREEN}$PASS${NC}"
echo -e "失败: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ 所有测试通过！系统运行正常。${NC}"
    exit 0
else
    echo -e "${RED}❌ 部分测试失败，请检查系统配置。${NC}"
    echo ""
    echo "排查建议："
    echo "1. 检查 API 是否启动: curl $API_URL/health"
    echo "2. 查看 API 日志: docker compose logs portal-api"
    echo "3. 检查数据库: docker compose ps postgres"
    echo "4. 查看环境变量: cat .env"
    exit 1
fi
