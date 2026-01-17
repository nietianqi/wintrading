# ⚡ 快速开始指南

## 🎯 两个问题的答案

### 1️⃣ 有什么快速部署的方法？

提供了 **3 种部署方式**，从简单到完整：

| 方式 | 适用场景 | 部署时间 | 命令 |
|------|----------|----------|------|
| **本地快速部署** | 开发测试 | 5 分钟 | `bash deploy-local.sh` |
| **Docker 部署** | 本地/服务器 | 10 分钟 | `docker compose up -d` |
| **服务器完整部署** | 生产环境 | 15 分钟 | `sudo bash deploy-server.sh` |

### 2️⃣ 这里面包含 Hummingbot 的功能了吗？

**回答**：包含了 **SaaS 平台控制面**，但需要集成官方 Hummingbot。

**已实现**（✅ 平台层）：
- 用户管理、订阅管理
- 为每个用户创建独立 Docker 栈
- Bot 管理接口
- 告警、备份、工单系统

**需要集成**（❌ 交易引擎）：
- Hummingbot 交易逻辑（使用官方 Docker 镜像）
- Hummingbot Dashboard
- 策略执行引擎

**集成指南**：查看 [`docs/HUMMINGBOT_INTEGRATION.md`](docs/HUMMINGBOT_INTEGRATION.md)

---

## 🚀 部署方式详解

### 方式 1：本地快速部署（推荐新手）

**适用场景**：本地开发、功能测试

**前置要求**：
- Python 3.10+
- Docker

**一键部署**：
```bash
cd saas-platform
bash deploy-local.sh
```

**脚本会自动**：
1. ✅ 检查依赖（Python、Docker）
2. ✅ 创建 Python 虚拟环境
3. ✅ 安装依赖
4. ✅ 生成环境变量（.env）
5. ✅ 启动 PostgreSQL（Docker）
6. ✅ 初始化数据库

**启动 API**：
```bash
source venv/bin/activate
python api/main.py
```

**访问**：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

**默认管理员**：
- 邮箱：`admin@yourdomain.com`
- 密码：`changeme123`

---

### 方式 2：Docker Compose 部署

**适用场景**：本地测试、小型部署

**前置要求**：
- Docker
- Docker Compose

**步骤**：

1️⃣ **配置环境变量**：
```bash
cd saas-platform
cp .env.example .env

# 生成密钥
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env
python3 -c "import secrets, base64; print('ENCRYPTION_MASTER_KEY=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" >> .env

# 编辑 .env，添加以下配置
nano .env
```

必填项：
```bash
DB_PASSWORD=your_secure_password
REDIS_PASSWORD=your_redis_password
BASE_DOMAIN=localhost  # 或你的域名
ADMIN_EMAIL=admin@yourdomain.com
```

2️⃣ **构建并启动**：
```bash
docker compose up -d
```

3️⃣ **初始化数据库**：
```bash
docker compose exec portal-api python scripts/init_system.py
```

4️⃣ **查看状态**：
```bash
docker compose ps
docker compose logs -f portal-api
```

**访问**：
- Portal API：http://localhost:8000/docs
- Traefik Dashboard：http://localhost:8080

**停止服务**：
```bash
docker compose down
```

**完全清理**（包括数据）：
```bash
docker compose down -v
```

---

### 方式 3：服务器完整部署（生产环境）

**适用场景**：正式生产环境、多用户

**前置要求**：
- Ubuntu 22.04 LTS 服务器
- Root 权限
- 域名（已配置 DNS）

**一键部署**：
```bash
# SSH 登录服务器
ssh root@your-server-ip

# 下载部署脚本
wget https://raw.githubusercontent.com/yourusername/hummingbot-saas/main/saas-platform/deploy-server.sh

# 执行部署
sudo bash deploy-server.sh
```

**脚本会自动**：
1. ✅ 安装 Docker
2. ✅ 创建项目目录（/opt/hummingbot-saas）
3. ✅ 配置环境变量
4. ✅ 启动所有服务（Portal、DB、Redis、Traefik）
5. ✅ 初始化数据库
6. ✅ 配置防火墙
7. ✅ 配置定时任务（备份、清理、健康检查）

**DNS 配置**（部署前）：
```
A    @              -> 服务器 IP
A    *.yourdomain.com -> 服务器 IP
A    api            -> 服务器 IP
```

**访问**：
- Portal API：https://api.yourdomain.com
- API 文档：https://api.yourdomain.com/docs
- Traefik Dashboard：http://your-server-ip:8080

**SSL 证书**：Traefik 自动申请 Let's Encrypt 证书

---

## 📝 部署后的必做任务

### 1. 修改管理员密码

```bash
# 通过 API 修改（访问 /docs）
# 或直接在数据库中修改
docker compose exec postgres psql -U postgres -d hummingbot_saas -c \
  "UPDATE users SET password_hash = 'new_hash' WHERE email = 'admin@yourdomain.com'"
```

### 2. 配置邮件通知（重要！）

编辑 `.env`：
```bash
# Gmail 示例
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password  # 不是邮箱密码！
FROM_EMAIL=noreply@yourdomain.com
```

**获取 Gmail App Password**：
1. 登录 Gmail
2. 账户设置 → 安全性
3. 两步验证 → 应用专用密码
4. 生成密码并复制

重启服务：
```bash
docker compose restart portal-api
```

### 3. 配置 Telegram 通知（可选）

1. 创建 Bot：
   - 私聊 [@BotFather](https://t.me/BotFather)
   - 发送 `/newbot`
   - 设置名称
   - 获取 Token

2. 配置 `.env`：
```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

3. 获取 Chat ID：
   - 私聊你的 Bot 发送 `/start`
   - 访问：`https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 查看 `chat.id`

---

## 🧪 测试部署

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

预期响应：
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00",
  "service": "hummingbot-saas-portal"
}
```

### 2. 创建测试用户

访问 http://localhost:8000/docs，测试：

**注册用户**：
```bash
POST /auth/register
{
  "email": "test@example.com",
  "username": "testuser",
  "password": "password123",
  "full_name": "Test User"
}
```

**登录**：
```bash
POST /auth/login
{
  "email": "test@example.com",
  "password": "password123"
}
```

复制返回的 `access_token`。

### 3. 创建租户（客户栈）

```bash
POST /tenants/provision
Authorization: Bearer <your_token>
```

**检查租户状态**：
```bash
GET /tenants/me
Authorization: Bearer <your_token>
```

### 4. 查看日志

```bash
# 所有服务
docker compose logs -f

# 仅 Portal API
docker compose logs -f portal-api

# 仅数据库
docker compose logs -f postgres
```

---

## 🐛 常见问题

### 问题 1：端口被占用

```bash
# 检查端口占用
sudo lsof -i :8000

# 终止进程
sudo kill -9 <PID>
```

### 问题 2：数据库连接失败

```bash
# 检查数据库状态
docker compose ps postgres

# 查看数据库日志
docker compose logs postgres

# 重启数据库
docker compose restart postgres
```

### 问题 3：无法访问 API

```bash
# 检查防火墙
sudo ufw status

# 开放端口
sudo ufw allow 8000/tcp

# 检查容器网络
docker network ls
docker network inspect saas-platform_portal-network
```

### 问题 4：SSL 证书申请失败

**原因**：DNS 未正确配置或 80/443 端口未开放

**解决**：
```bash
# 检查 DNS
dig api.yourdomain.com

# 检查端口
sudo netstat -tuln | grep 80
sudo netstat -tuln | grep 443

# 查看 Traefik 日志
docker compose logs traefik
```

---

## 📊 性能测试

### 单用户负载测试

```bash
# 安装 Apache Bench
sudo apt install apache2-utils

# 测试 API 性能
ab -n 1000 -c 10 http://localhost:8000/health
```

### 多租户压力测试

```bash
# 创建 100 个测试用户
for i in {1..100}; do
  curl -X POST http://localhost:8000/auth/register \
    -H "Content-Type: application/json" \
    -d "{
      \"email\": \"user$i@test.com\",
      \"username\": \"user$i\",
      \"password\": \"password123\"
    }"
done
```

---

## 📚 下一步

1. ✅ **集成 Hummingbot**：查看 [`docs/HUMMINGBOT_INTEGRATION.md`](docs/HUMMINGBOT_INTEGRATION.md)
2. ✅ **配置支付**：集成 Stripe/PayPal
3. ✅ **开发前端**：React/Vue Dashboard
4. ✅ **监控告警**：Prometheus + Grafana
5. ✅ **备份测试**：验证备份恢复流程

---

## 🆘 获取帮助

- 📖 完整文档：[README.md](README.md)
- 🚀 部署指南：[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- 🤖 Hummingbot 集成：[docs/HUMMINGBOT_INTEGRATION.md](docs/HUMMINGBOT_INTEGRATION.md)
- 📝 项目总结：[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- 💬 GitHub Issues：提交问题
- 📧 邮箱：support@yourdomain.com

---

**祝部署顺利！🎉**
