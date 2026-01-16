# 🚀 Hummingbot SaaS Platform

将 Hummingbot 做成托管 SaaS 服务的完整解决方案。

## 📋 目录

- [核心功能](#核心功能)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [部署指南](#部署指南)
- [API 文档](#api-文档)
- [运维管理](#运维管理)

---

## 🎯 核心功能

### 用户端功能
- ✅ **用户注册与登录**：邮箱验证、JWT 认证
- ✅ **订阅管理**：Free / Basic / Pro / Premium 套餐
- ✅ **独立客户栈**：每个用户独立的 Hummingbot 运行环境
- ✅ **Bot 管理**：创建、启动、停止、监控 Bot
- ✅ **策略模板**：Grid / DCA / Signal Webhook
- ✅ **交易所连接**：加密存储 API Keys
- ✅ **实时告警**：邮件 + Telegram 通知
- ✅ **工单系统**：技术支持与问题跟踪

### 运营端功能
- ✅ **客户栈编排**：自动化创建、升级、回滚
- ✅ **资源监控**：CPU、内存、容器状态
- ✅ **备份恢复**：自动备份 + 一键恢复
- ✅ **配额管理**：Bot 数量、资源限制、功能权限
- ✅ **计费系统**：订阅、续费、宽限期管理

---

## 🏗️ 架构设计

### 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户（通过浏览器）                        │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                       Traefik (反向代理 + TLS)                   │
└───────┬────────────────────┬──────────────────────────────────┘
        │                    │
        ▼                    ▼
┌──────────────┐    ┌────────────────────────────────────────┐
│ Portal API   │    │  客户栈 (每个用户独立)                   │
│ (FastAPI)    │    │  ┌──────────────────────────────────┐  │
│              │    │  │ u123.domain.com (Dashboard)      │  │
│ - 用户管理   │    │  │ api-u123.domain.com (HB API)     │  │
│ - 订阅管理   │    │  │                                  │  │
│ - Bot 管理   │    │  │ ┌────────┐  ┌──────────────┐    │  │
│ - 告警通知   │    │  │ │ HB API │  │ HB Dashboard │    │  │
│ - 工单系统   │    │  │ └────────┘  └──────────────┘    │  │
│              │    │  │ ┌──────────┐  ┌────────┐        │  │
└──────┬───────┘    │  │ │ Postgres │  │ Redis  │        │  │
       │            │  │ └──────────┘  └────────┘        │  │
       ▼            │  └──────────────────────────────────┘  │
┌──────────────┐    └────────────────────────────────────────┘
│ PostgreSQL   │
│ (Portal DB)  │
└──────────────┘
```

### 技术栈

- **后端框架**：FastAPI + SQLAlchemy
- **数据库**：PostgreSQL (Portal 共享 + 每客户独立)
- **容器编排**：Docker + Docker Compose
- **反向代理**：Traefik (自动 TLS)
- **任务队列**：Celery + Redis (可选)
- **监控**：Prometheus + Grafana (可选)

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis (可选)

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/hummingbot-saas.git
cd hummingbot-saas
```

### 2. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入实际配置
```

**重要配置项：**

```bash
# 生成 JWT 密钥
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成加密主密钥
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

### 4. 初始化数据库

```bash
python -c "from database import init_database; init_database()"
```

### 5. 启动 Portal API

```bash
python api/main.py
```

访问：http://localhost:8000/docs

---

## 📦 部署指南

### 生产环境部署（推荐使用 Docker）

#### 1. 部署 Portal API

```yaml
# docker-compose.portal.yml
version: '3.8'

services:
  portal-api:
    build: .
    container_name: hummingbot-portal-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - /srv/tenants:/srv/tenants
      - /srv/backups:/srv/backups
      - /var/run/docker.sock:/var/run/docker.sock  # 用于管理客户栈
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:15-alpine
    container_name: hummingbot-portal-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: hummingbot_saas
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - portal_db:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    container_name: hummingbot-portal-redis
    restart: unless-stopped

  traefik:
    image: traefik:v2.10
    container_name: traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./traefik.yml:/etc/traefik/traefik.yml
      - ./acme.json:/acme.json
      - /var/run/docker.sock:/var/run/docker.sock:ro

volumes:
  portal_db:
```

启动：

```bash
docker-compose -f docker-compose.portal.yml up -d
```

#### 2. 配置 Traefik（自动 HTTPS）

```yaml
# traefik.yml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https

  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: admin@yourdomain.com
      storage: /acme.json
      httpChallenge:
        entryPoint: web

providers:
  docker:
    exposedByDefault: false
    network: web
```

#### 3. 定时任务（Cron）

```bash
# /etc/cron.d/hummingbot-saas

# 每天凌晨 2 点自动备份
0 2 * * * /usr/local/bin/python /app/scripts/daily_backup.py

# 每天凌晨 3 点清理过期备份
0 3 * * * /usr/local/bin/python /app/scripts/cleanup_backups.py

# 每 5 分钟检查租户健康状态
*/5 * * * * /usr/local/bin/python /app/scripts/health_check.py
```

---

## 📡 API 文档

### 认证

所有受保护的接口需要在 Header 中携带 JWT Token：

```
Authorization: Bearer <your-jwt-token>
```

### 主要接口

#### 用户认证

```bash
# 注册
POST /auth/register
{
  "email": "user@example.com",
  "username": "testuser",
  "password": "securepassword123"
}

# 登录
POST /auth/login
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

#### 订阅管理

```bash
# 获取我的订阅
GET /subscriptions/me

# 升级订阅
POST /subscriptions/upgrade
{
  "new_tier": "pro",
  "payment_method_id": "pm_xxxxx"
}
```

#### 租户管理

```bash
# 创建客户栈
POST /tenants/provision

# 获取我的租户信息
GET /tenants/me
```

#### Bot 管理

```bash
# 创建 Bot
POST /bots
{
  "bot_name": "My Grid Bot",
  "exchange_connection_id": "conn-123",
  "strategy_template": "grid",
  "strategy_config": {
    "lower_bound": 30000,
    "upper_bound": 35000,
    "grid_count": 10,
    "order_amount": 100
  },
  "trading_pair": "BTC-USDT"
}

# 启动 Bot
POST /bots/{bot_id}/start

# 停止 Bot
POST /bots/{bot_id}/stop

# 获取 Bot 列表
GET /bots
```

---

## 🔧 运维管理

### 监控租户健康状态

```python
from core.orchestrator import TenantOrchestrator

orchestrator = TenantOrchestrator()
health = orchestrator.check_tenant_health("tenant-id")
print(health)
```

### 升级客户栈

```python
# 升级到新版本
orchestrator.upgrade_tenant_stack(
    tenant_id="tenant-id",
    new_version="1.2.0",
    backup_first=True
)
```

### 手动备份

```python
from core.backup import BackupManager

backup_mgr = BackupManager()
backup = backup_mgr.create_backup(
    tenant_id="tenant-id",
    backup_type="full",
    include_logs=False
)
```

### 恢复备份

```python
backup_mgr.restore_backup(
    backup_id="backup-id",
    tenant_id="tenant-id"
)
```

---

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_orchestrator.py

# 查看覆盖率
pytest --cov=. --cov-report=html
```

---

## 📊 数据库迁移

```bash
# 创建迁移
alembic revision --autogenerate -m "Add new field"

# 执行迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

---

## 🔐 安全最佳实践

1. **密钥管理**
   - ✅ 使用环境变量存储敏感信息
   - ✅ 永远不要将 `.env` 提交到 Git
   - ✅ 生产环境使用 AWS KMS / HashiCorp Vault

2. **API Keys 加密**
   - ✅ 使用 AES-GCM 加密
   - ✅ 每条记录独立 nonce
   - ✅ 支持密钥轮换

3. **网络隔离**
   - ✅ 客户栈使用独立 Docker Network
   - ✅ 数据库不对外暴露
   - ✅ Traefik 统一入口 + TLS

4. **访问控制**
   - ✅ JWT 认证
   - ✅ 最低权限原则
   - ✅ 操作审计日志

---

## 📈 性能优化

### 数据库优化
- 为查询频繁的字段添加索引
- 使用连接池（SQLAlchemy QueuePool）
- 定期 VACUUM 和 ANALYZE

### 容器资源限制
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
```

### 缓存策略
- Redis 缓存热数据
- 静态资源 CDN
- API 响应缓存（短期）

---

## 🐛 常见问题

### 1. 容器无法启动

**问题**：`docker compose up` 失败

**解决**：
```bash
# 查看日志
docker compose logs -f

# 检查端口占用
netstat -tuln | grep 8000

# 清理旧容器
docker compose down -v
```

### 2. 数据库连接失败

**问题**：`psycopg2.OperationalError: could not connect to server`

**解决**：
```bash
# 检查 PostgreSQL 是否运行
docker compose ps

# 检查数据库配置
echo $DATABASE_URL

# 测试连接
psql $DATABASE_URL -c "SELECT 1"
```

### 3. 租户栈创建失败

**问题**：`TenantOrchestrator` 报错

**解决**：
```bash
# 检查目录权限
ls -la /srv/tenants

# 检查 Docker 权限
docker ps

# 查看详细日志
tail -f /srv/tenants/u123/logs/hummingbot.log
```

---

## 📝 待办事项

- [ ] 前端 Dashboard（React / Vue）
- [ ] 支付集成（Stripe / PayPal）
- [ ] 多语言支持（i18n）
- [ ] 移动端 App
- [ ] 策略市场（用户可分享策略）
- [ ] 白标功能（White-label）
- [ ] 更多策略模板（Arbitrage / Market Making）

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📞 联系方式

- 邮箱：support@yourdomain.com
- Telegram：@yourtelegram
- 官网：https://yourdomain.com

---

**祝你的 Hummingbot SaaS 生意兴隆！🚀**
