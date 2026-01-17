# 🚀 完整运行指南 - 包含 Hummingbot

## 📋 目录

- [快速开始](#快速开始)
- [本地开发环境](#本地开发环境)
- [生产环境部署](#生产环境部署-1000用户)
- [创建第一个 Bot](#创建第一个-bot)
- [故障排查](#故障排查)

---

## ⚡ 快速开始（5分钟运行）

### 前置要求

```bash
# 检查依赖
docker --version   # >= 24.0
docker compose version  # >= 2.20
python3 --version  # >= 3.10
```

### 一键启动

```bash
# 1. 进入项目目录
cd saas-platform

# 2. 运行完整系统（包含 Hummingbot）
chmod +x run-complete.sh
bash run-complete.sh
```

**脚本会自动**：
1. ✅ 检查依赖
2. ✅ 生成环境变量（密钥、密码）
3. ✅ 启动数据库和 Redis
4. ✅ 初始化数据库（创建表、管理员账号）
5. ✅ 启动 Portal API
6. ✅ 启动 Traefik（反向代理）
7. ✅ 创建测试租户（演示 Hummingbot 集成）

**完成后访问**：
- API 文档：http://localhost:8000/docs
- Traefik 仪表盘：http://localhost:8080

---

## 💻 本地开发环境

### 方式 1：Docker Compose（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env

# 生成密钥
python3 << EOF
import secrets, base64
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"ENCRYPTION_MASTER_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}")
print(f"DB_PASSWORD={secrets.token_urlsafe(16)}")
print(f"REDIS_PASSWORD={secrets.token_urlsafe(16)}")
EOF

# 将输出添加到 .env

# 2. 启动所有服务
docker compose up -d

# 3. 初始化数据库
docker compose exec portal-api python scripts/init_system.py

# 4. 查看日志
docker compose logs -f
```

### 方式 2：Python 本地运行（开发调试）

```bash
# 1. 启动数据库和 Redis
docker compose up -d postgres redis

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 初始化数据库
python scripts/init_system.py

# 5. 启动 Portal API
python api/main.py

# 另开终端：启动 Celery Worker（可选）
celery -A core.tasks worker --loglevel=info
```

---

## 🏢 生产环境部署（1000用户）

### 服务器配置推荐

根据 [PRODUCTION_ARCHITECTURE.md](PRODUCTION_ARCHITECTURE.md) 的分析：

#### 方案 B：多机集群（推荐）

**服务器列表**：

| 角色 | 数量 | 配置 | 月成本 |
|------|------|------|--------|
| Portal 服务器 | 1 | 16核 64GB | $150-200 |
| Worker 节点 | 5 | 32核 128GB | $1,500-2,000 |
| 数据库（主+从） | 2 | 16核 64GB | $400 |
| Redis | 1 | 8核 32GB | $100 |
| 对象存储 | - | 1TB S3 | $50-100 |
| **总计** | **9** | - | **$2,200-2,800** |

**支持容量**：
- 1,000-1,500 活跃用户
- 4,000-5,000 运行中的 Bot
- 同时在线：600-800 用户

### 部署步骤

#### 1. Portal 服务器

```bash
# SSH 登录 Portal 服务器
ssh root@portal-server-ip

# 下载部署脚本
wget https://raw.githubusercontent.com/yourusername/hummingbot-saas/main/saas-platform/deploy-server.sh

# 执行部署
chmod +x deploy-server.sh
./deploy-server.sh

# 等待完成...
```

#### 2. Worker 节点（每台执行）

```bash
# SSH 登录 Worker 节点
ssh root@worker-01-ip

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 创建数据目录
mkdir -p /srv/tenants /srv/backups

# 启动 Worker Agent（连接到 Portal）
docker run -d \
  --name hummingbot-worker-agent \
  --restart always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /srv/tenants:/srv/tenants \
  -e PORTAL_URL=https://api.yourdomain.com \
  -e WORKER_TOKEN=<从 Portal 获取> \
  hummingbot-saas/worker-agent:latest

# 验证连接
docker logs -f hummingbot-worker-agent
```

#### 3. 配置 DNS

```dns
# A 记录
@                   IN A    portal-server-ip
*.yourdomain.com    IN A    portal-server-ip
api                 IN A    portal-server-ip
traefik             IN A    portal-server-ip
grafana             IN A    portal-server-ip
prometheus          IN A    portal-server-ip
```

#### 4. 启动生产配置

```bash
# 在 Portal 服务器上
cd /opt/hummingbot-saas

# 使用生产配置
docker compose -f docker-compose.production.yml up -d

# 查看状态
docker compose -f docker-compose.production.yml ps

# 查看日志
docker compose -f docker-compose.production.yml logs -f portal-api
```

#### 5. 配置监控（可选）

```bash
# 启动 Prometheus + Grafana
docker compose -f docker-compose.production.yml --profile with-monitoring up -d

# 访问 Grafana
open https://grafana.yourdomain.com
# 默认：admin / <GRAFANA_PASSWORD from .env>

# 导入仪表盘
# 1. 登录 Grafana
# 2. Import → Upload dashboard.json
# 3. 选择 config/grafana/dashboards/hummingbot-saas.json
```

---

## 🤖 创建第一个 Bot

### 步骤 1：注册用户

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "trader@example.com",
    "username": "trader1",
    "password": "SecurePassword123!",
    "full_name": "Demo Trader"
  }'
```

### 步骤 2：登录获取 Token

```bash
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "trader@example.com",
    "password": "SecurePassword123!"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')
echo "Token: $TOKEN"
```

### 步骤 3：创建租户（客户栈）

```bash
curl -X POST http://localhost:8000/tenants/provision \
  -H "Authorization: Bearer $TOKEN"

# 响应示例
{
  "id": "tenant-uuid",
  "tenant_code": "u12345678",
  "subdomain": "u12345678.yourdomain.com",
  "dashboard_url": "https://u12345678.yourdomain.com",
  "status": "provisioning"
}
```

**等待几分钟，租户栈会自动创建**：
- PostgreSQL 容器
- Redis 容器
- Hummingbot 容器
- Dashboard 容器

```bash
# 检查租户状态
curl http://localhost:8000/tenants/me \
  -H "Authorization: Bearer $TOKEN"

# 查看容器
docker ps | grep u12345678
```

### 步骤 4：添加交易所连接

```bash
curl -X POST http://localhost:8000/exchange-connections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "exchange_name": "binance",
    "connection_name": "My Binance Account",
    "api_key": "your_binance_api_key",
    "api_secret": "your_binance_api_secret"
  }'

# 响应
{
  "id": "exchange-conn-uuid",
  "exchange_name": "binance",
  "connection_name": "My Binance Account",
  "is_active": true
}
```

**安全提示**：
- API Key 会被 AES-GCM 加密存储
- 数据库只保存密文
- 建议只给交易权限，不给提现权限

### 步骤 5：创建 Grid Bot

```bash
curl -X POST http://localhost:8000/bots \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "BTC Grid Bot",
    "description": "Bitcoin grid trading strategy",
    "exchange_connection_id": "exchange-conn-uuid",
    "strategy_template": "grid",
    "trading_pair": "BTC-USDT",
    "market_type": "spot",
    "strategy_config": {
      "lower_bound": 30000,
      "upper_bound": 35000,
      "grid_count": 10,
      "order_amount": 100
    },
    "risk_config": {
      "max_position_usd": 5000,
      "max_loss_daily_usd": 200,
      "circuit_breaker_enabled": true
    }
  }'

# 响应
{
  "id": "bot-uuid",
  "bot_name": "BTC Grid Bot",
  "status": "stopped",
  "strategy_template": "grid",
  "trading_pair": "BTC-USDT",
  "created_at": "2024-01-16T10:00:00Z"
}
```

### 步骤 6：启动 Bot

```bash
curl -X POST http://localhost:8000/bots/bot-uuid/start \
  -H "Authorization: Bearer $TOKEN"

# 响应
{
  "message": "Bot is starting..."
}
```

**背后发生的事情**：

1. Portal API 解密交易所凭证
2. 生成 Hummingbot 配置文件：
   ```yaml
   # /srv/tenants/u12345678/configs/conf_global.yml
   binance_api_key: your_api_key
   binance_secret_key: your_api_secret
   kill_switch_enabled: true
   kill_switch_rate: -0.20
   ```

3. 生成策略脚本：
   ```python
   # /srv/tenants/u12345678/scripts/bot-uuid.py
   class GridStrategy(ScriptStrategyBase):
       exchange = "binance"
       trading_pair = "BTC-USDT"
       grid_count = 10
       lower_bound = Decimal("30000")
       upper_bound = Decimal("35000")
       # ... 策略逻辑
   ```

4. 启动 Hummingbot：
   ```bash
   docker exec u12345678-hummingbot \
     python /home/hummingbot/scripts/bot-uuid.py
   ```

5. Bot 开始运行：
   - 初始化网格价格水平
   - 在网格上下限之间放置买卖订单
   - 订单成交后自动重新下单
   - 监控风控限制

### 步骤 7：监控 Bot

```bash
# 查看 Bot 状态
curl http://localhost:8000/bots/bot-uuid \
  -H "Authorization: Bearer $TOKEN"

# 响应
{
  "id": "bot-uuid",
  "status": "running",
  "total_pnl": 15.32,
  "total_trades": 24,
  "win_rate": 0.67,
  "running_time_seconds": 3600,
  "started_at": "2024-01-16T10:00:00Z"
}

# 查看告警
curl http://localhost:8000/alerts \
  -H "Authorization: Bearer $TOKEN"

# 查看日志
docker logs u12345678-hummingbot
```

### 步骤 8：访问 Dashboard

打开浏览器：
```
https://u12345678.yourdomain.com
```

**Dashboard 功能**：
- 实时 PnL 图表
- 订单簿可视化
- 持仓管理
- 订单历史
- 策略参数调整

### 步骤 9：停止 Bot

```bash
curl -X POST http://localhost:8000/bots/bot-uuid/stop \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🧪 测试系统

### 自动化测试

```bash
# 运行部署测试
bash test-deployment.sh

# 输出示例
🧪 Hummingbot SaaS 部署测试
====================================
1️⃣ 基础健康检查
测试: 健康检查接口 ... ✓ PASS (HTTP 200)
测试: 根路径 ... ✓ PASS (HTTP 200)
测试: API 文档 ... ✓ PASS (HTTP 200)

2️⃣ 认证接口
测试: 注册接口（需要参数） ... ✓ PASS (HTTP 422)
测试: 登录接口（需要参数） ... ✓ PASS (HTTP 422)

...

✅ 所有测试通过！系统运行正常。
```

### 手动测试

#### 1. 测试 Portal API

```bash
# 健康检查
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs
```

#### 2. 测试数据库

```bash
# 连接数据库
docker compose exec postgres psql -U postgres -d hummingbot_saas

# 查看表
\dt

# 查看用户
SELECT id, email, username, is_active FROM users;

# 查看租户
SELECT tenant_code, status, dashboard_url FROM tenants;
```

#### 3. 测试租户栈

```bash
# 查看所有租户容器
docker ps --filter "name=u" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 进入 Hummingbot 容器
docker exec -it u12345678-hummingbot bash

# 查看 Hummingbot 日志
tail -f logs/hummingbot.log

# 查看配置
cat conf/conf_global.yml

# 查看策略脚本
cat scripts/bot-uuid.py
```

#### 4. 测试 Dashboard

```bash
# 查看 Dashboard 日志
docker logs -f u12345678-dashboard

# 访问 Dashboard
open https://u12345678.yourdomain.com
```

---

## 🐛 故障排查

### 问题 1：Portal API 无法启动

**症状**：
```bash
docker compose logs portal-api
# Error: Unable to connect to database
```

**解决**：
```bash
# 1. 检查数据库是否启动
docker compose ps postgres

# 2. 测试数据库连接
docker compose exec postgres pg_isready -U postgres

# 3. 检查 .env 配置
grep DATABASE_URL .env

# 4. 重启服务
docker compose restart portal-api
```

### 问题 2：租户创建失败

**症状**：
```json
{
  "status": "error",
  "message": "Failed to provision tenant"
}
```

**解决**：
```bash
# 1. 检查 Docker 权限
docker ps

# 2. 检查目录权限
ls -la /srv/tenants

# 3. 查看详细日志
docker compose logs orchestrator

# 4. 手动创建测试租户
python3 -c "
from core.orchestrator import TenantOrchestrator
orch = TenantOrchestrator()
orch.provision_tenant_stack('tenant-id-here')
"
```

### 问题 3：Bot 无法启动

**症状**：
```json
{
  "status": "error",
  "last_error": "Failed to start strategy"
}
```

**解决**：
```bash
# 1. 检查 Hummingbot 容器状态
docker ps | grep hummingbot

# 2. 查看 Hummingbot 日志
docker logs u12345678-hummingbot

# 3. 进入容器排查
docker exec -it u12345678-hummingbot bash

# 4. 检查策略脚本
cat /home/hummingbot/scripts/bot-uuid.py

# 5. 手动运行策略
python3 /home/hummingbot/scripts/bot-uuid.py
```

### 问题 4：Dashboard 无法访问

**症状**：
```
502 Bad Gateway
```

**解决**：
```bash
# 1. 检查 Dashboard 容器
docker ps | grep dashboard

# 2. 查看 Dashboard 日志
docker logs u12345678-dashboard

# 3. 检查 Traefik 路由
curl -H "Host: u12345678.yourdomain.com" http://localhost

# 4. 检查 DNS
dig u12345678.yourdomain.com

# 5. 重启 Dashboard
docker restart u12345678-dashboard
```

### 问题 5：高负载/性能问题

**症状**：
```
API 响应慢
CPU 100%
内存不足
```

**解决**：
```bash
# 1. 查看资源使用
docker stats

# 2. 查看数据库慢查询
docker compose exec postgres psql -U postgres -d hummingbot_saas -c "
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
"

# 3. 优化数据库
docker compose exec postgres psql -U postgres -d hummingbot_saas -c "
VACUUM ANALYZE;
REINDEX DATABASE hummingbot_saas;
"

# 4. 增加资源限制
# 编辑 docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '8.0'
      memory: 16G

# 5. 启用休眠机制
# 自动停止闲置 7 天的租户
```

---

## 📊 生产环境检查清单

### 上线前

- [ ] 修改所有默认密码
- [ ] 配置 SMTP 邮件通知
- [ ] 配置 Telegram Bot（可选）
- [ ] 配置域名和 DNS
- [ ] 申请 SSL 证书（Traefik 自动）
- [ ] 配置防火墙
- [ ] 设置数据库备份（每日）
- [ ] 配置监控告警
- [ ] 压力测试
- [ ] 安全审计

### 上线后

- [ ] 监控系统资源（CPU、内存、磁盘）
- [ ] 监控 API 响应时间
- [ ] 监控错误率
- [ ] 检查备份成功率
- [ ] 检查告警通知
- [ ] 审查访问日志
- [ ] 更新系统补丁
- [ ] 轮换密钥（每月）

---

## 📚 相关文档

- [快速开始](../QUICKSTART.md)
- [生产架构](PRODUCTION_ARCHITECTURE.md)
- [Hummingbot 集成](HUMMINGBOT_INTEGRATION.md)
- [部署指南](DEPLOYMENT.md)
- [项目总结](../PROJECT_SUMMARY.md)

---

**🎉 祝你运行顺利！**

有问题随时查看文档或提交 Issue。
