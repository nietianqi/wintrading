# 🤖 Hummingbot 集成指南

## 📌 重要说明

**当前实现了什么？**

✅ **SaaS 平台控制面**（已完成）：
- 用户注册、登录、订阅管理
- 为每个用户创建独立的 Docker 栈
- Bot 管理接口（创建、启动、停止）
- 告警、备份、工单系统
- 自动化运维（编排、升级、回滚）

❌ **Hummingbot 交易引擎**（需要集成）：
- Hummingbot 的实际交易逻辑
- Hummingbot Dashboard
- Hummingbot API

---

## 🏗️ 架构说明

```
┌─────────────────────────────────────────────────────┐
│          我们的 SaaS 平台（Portal）                   │
│  ┌──────────────────────────────────────────────┐  │
│  │ 用户管理、订阅、Bot 管理、告警、备份           │  │
│  └──────────────────┬───────────────────────────┘  │
│                     │                               │
│                     │ 编排和管理                    │
│                     ▼                               │
│  ┌──────────────────────────────────────────────┐  │
│  │         客户栈（每个用户独立）                 │  │
│  │  ┌────────────────────────────────────────┐  │  │
│  │  │  Hummingbot Container（官方镜像）       │  │  │
│  │  │  ├── Hummingbot Core（交易引擎）        │  │  │
│  │  │  ├── Hummingbot Gateway（可选）         │  │  │
│  │  │  └── 策略脚本                           │  │  │
│  │  ├────────────────────────────────────────┤  │  │
│  │  │  Hummingbot Dashboard（官方镜像）       │  │  │
│  │  ├────────────────────────────────────────┤  │  │
│  │  │  PostgreSQL（租户数据库）               │  │  │
│  │  └────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**我们的平台作用**：
1. 自动为每个用户创建和管理这些容器
2. 提供统一的用户界面和 API
3. 处理订阅、计费、告警、备份
4. 监控和维护 Hummingbot 实例

**Hummingbot 作用**：
1. 实际执行交易策略
2. 连接交易所
3. 管理订单、仓位
4. 提供 Dashboard 可视化

---

## 🚀 集成步骤

### 方式 1：使用官方 Hummingbot Docker 镜像（推荐）

#### 步骤 1：更新客户栈 Docker Compose 模板

编辑 `core/orchestrator.py` 中的 `_get_default_compose_template()` 方法，已经包含了 Hummingbot 镜像：

```yaml
services:
  hummingbot-api:
    image: hummingbot/hummingbot:latest
    # ... 其他配置
```

#### 步骤 2：配置 Hummingbot

官方 Hummingbot 使用配置文件方式，我们需要在创建 Bot 时生成配置文件：

```python
# 在 core/orchestrator.py 中添加
def _generate_hummingbot_config(self, bot: Bot) -> dict:
    """生成 Hummingbot 策略配置"""

    if bot.strategy_template == StrategyTemplate.GRID:
        return {
            "strategy": "pure_market_making",  # 或 grid_trading
            "exchange": bot.exchange_connection.exchange_name,
            "market": bot.trading_pair,
            "order_amount": bot.strategy_config["order_amount"],
            "bid_spread": bot.strategy_config.get("bid_spread", 0.001),
            "ask_spread": bot.strategy_config.get("ask_spread", 0.001),
            # ... 更多参数
        }
```

#### 步骤 3：启动 Hummingbot

```python
def start_hummingbot_bot(self, bot_id: str):
    """启动 Hummingbot Bot"""

    with get_db() as db:
        bot = db.query(Bot).filter(Bot.id == bot_id).first()
        tenant = db.query(Tenant).filter(Tenant.id == bot.tenant_id).first()

        # 1. 生成配置文件
        config = self._generate_hummingbot_config(bot)
        config_path = Path(tenant.deployment_path) / "configs" / f"{bot.id}.yml"

        with config_path.open('w') as f:
            yaml.dump(config, f)

        # 2. 启动 Hummingbot
        container_name = f"{tenant.tenant_code}-hummingbot"

        result = subprocess.run([
            "docker", "exec", container_name,
            "hummingbot", "start", "--script", f"{bot.id}.yml"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            bot.status = BotStatus.RUNNING
            bot.started_at = datetime.utcnow()
            db.commit()
```

---

### 方式 2：使用 Hummingbot Gateway（高级）

如果需要支持更多交易所（特别是 DEX），可以集成 Hummingbot Gateway：

```yaml
# 在客户栈 compose 中添加
services:
  hummingbot-gateway:
    image: hummingbot/gateway:latest
    container_name: {{ tenant_code }}-gateway
    restart: unless-stopped
    environment:
      GATEWAY_PASSPHRASE: {{ gateway_passphrase }}
    volumes:
      - ./data/gateway:/home/gateway/conf
    networks:
      - tenant_network
    ports:
      - "15888:15888"
```

---

## 📝 完整集成示例

### 1. 创建完整的客户栈配置

创建文件：`core/templates/tenant-compose-with-hummingbot.yml.j2`

```yaml
version: '3.8'

services:
  # PostgreSQL
  postgres:
    image: postgres:15-alpine
    container_name: {{ tenant_code }}-postgres
    environment:
      POSTGRES_DB: hummingbot
      POSTGRES_USER: hummingbot
      POSTGRES_PASSWORD: {{ postgres_password }}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    networks:
      - tenant_network

  # Redis
  redis:
    image: redis:7-alpine
    container_name: {{ tenant_code }}-redis
    command: redis-server --requirepass {{ redis_password }}
    volumes:
      - ./data/redis:/data
    networks:
      - tenant_network

  # Hummingbot Core
  hummingbot:
    image: hummingbot/hummingbot:{{ hummingbot_version }}
    container_name: {{ tenant_code }}-hummingbot
    restart: unless-stopped
    environment:
      CONFIG_FILE_NAME: conf_global.yml
      CONFIG_PASSWORD: {{ hummingbot_password }}
    volumes:
      - ./data/hummingbot:/home/hummingbot/conf
      - ./configs:/home/hummingbot/scripts
      - ./logs:/home/hummingbot/logs
    networks:
      - tenant_network
    depends_on:
      - postgres
      - redis

  # Hummingbot Dashboard
  dashboard:
    image: hummingbot/dashboard:{{ dashboard_version }}
    container_name: {{ tenant_code }}-dashboard
    restart: unless-stopped
    environment:
      HUMMINGBOT_INSTANCE_ID: {{ tenant_code }}
    volumes:
      - ./data/hummingbot:/home/hummingbot/conf:ro
    networks:
      - tenant_network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.{{ tenant_code }}-dashboard.rule=Host(`{{ subdomain }}`)"
      - "traefik.http.routers.{{ tenant_code }}-dashboard.entrypoints=websecure"
      - "traefik.http.routers.{{ tenant_code }}-dashboard.tls.certresolver=letsencrypt"
    depends_on:
      - hummingbot

networks:
  tenant_network:
    driver: bridge
```

### 2. 更新 Bot 启动逻辑

编辑 `api/main.py`，在 `/bots/{bot_id}/start` 接口中：

```python
@app.post("/bots/{bot_id}/start")
def start_bot(
    bot_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """启动 Bot"""
    bot = db.query(Bot).filter(
        Bot.id == bot_id,
        Bot.user_id == current_user.id
    ).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found"
        )

    # 1. 获取交易所凭证（解密）
    from core.encryption import EncryptionManager
    encryptor = EncryptionManager()

    exchange_conn = db.query(ExchangeConnection).filter(
        ExchangeConnection.id == bot.exchange_connection_id
    ).first()

    credentials = encryptor.decrypt_api_credentials({
        "encrypted_api_key": exchange_conn.encrypted_api_key,
        "encrypted_api_secret": exchange_conn.encrypted_api_secret,
        "nonce_key": exchange_conn.nonce_key,
        "nonce_secret": exchange_conn.nonce_secret,
    })

    # 2. 生成 Hummingbot 配置文件
    tenant = db.query(Tenant).filter(Tenant.id == bot.tenant_id).first()
    config_path = Path(tenant.deployment_path) / "configs" / f"{bot.id}.py"

    # 生成策略脚本
    strategy_script = generate_strategy_script(bot, credentials)
    config_path.write_text(strategy_script)

    # 3. 启动 Hummingbot Bot
    from core.orchestrator import TenantOrchestrator
    orchestrator = TenantOrchestrator()
    orchestrator.start_hummingbot_bot(bot.id)

    bot.status = BotStatus.STARTING
    bot.started_at = datetime.utcnow()
    db.commit()

    return {"message": "Bot is starting..."}
```

### 3. 策略脚本生成器

创建文件：`core/strategy_generator.py`

```python
def generate_strategy_script(bot: Bot, credentials: dict) -> str:
    """
    生成 Hummingbot 策略脚本

    Hummingbot 支持两种方式：
    1. 配置文件（YAML）- 适合简单策略
    2. Python 脚本 - 适合复杂策略
    """

    if bot.strategy_template == StrategyTemplate.GRID:
        return f"""
from hummingbot.strategy.pure_market_making import PureMarketMakingStrategy
from hummingbot.connector.exchange_base import ExchangeBase
from decimal import Decimal

class GridStrategy(PureMarketMakingStrategy):
    def __init__(self):
        super().__init__(
            exchange="{bot.exchange_connection.exchange_name}",
            market="{bot.trading_pair}",
            bid_spread=Decimal("{bot.strategy_config['bid_spread']}"),
            ask_spread=Decimal("{bot.strategy_config['ask_spread']}"),
            order_amount=Decimal("{bot.strategy_config['order_amount']}"),
            # ... 更多参数
        )

    # 自定义逻辑
    def on_tick(self):
        # 检查风控
        if self.check_risk_limits():
            super().on_tick()
        else:
            self.logger.warning("Risk limits exceeded, stopping strategy")
            self.stop()

    def check_risk_limits(self):
        # 检查最大仓位、最大亏损等
        max_position = {bot.risk_config.get('max_position_usd', 10000)}
        current_position = self.get_position_value()
        return current_position < max_position

# 运行策略
strategy = GridStrategy()
"""

    elif bot.strategy_template == StrategyTemplate.DCA:
        # DCA 策略脚本
        pass

    elif bot.strategy_template == StrategyTemplate.SIGNAL_WEBHOOK:
        # Webhook 策略脚本
        pass
```

---

## 🔗 官方 Hummingbot 资源

- **官方文档**: https://docs.hummingbot.org
- **Docker 镜像**: https://hub.docker.com/r/hummingbot/hummingbot
- **GitHub**: https://github.com/hummingbot/hummingbot
- **Discord 社区**: https://discord.gg/hummingbot

---

## 📋 检查清单

在正式上线前，确保完成以下集成：

- [ ] 测试 Hummingbot 官方镜像启动
- [ ] 配置文件生成和加载
- [ ] 交易所 API 凭证注入
- [ ] Bot 启动/停止/重启功能
- [ ] 实时日志查看
- [ ] Dashboard 访问权限控制
- [ ] 策略模板验证
- [ ] 风控参数生效
- [ ] 告警集成（Hummingbot 错误 → 我们的告警系统）
- [ ] 性能测试（单租户 / 多租户）

---

## 🎯 快速测试

### 1. 本地测试单个 Hummingbot 实例

```bash
# 启动官方 Hummingbot
docker run -it \
  --name my-hummingbot \
  -v $(pwd)/hummingbot_conf:/conf \
  -v $(pwd)/hummingbot_logs:/logs \
  hummingbot/hummingbot:latest

# 进入容器
docker exec -it my-hummingbot bash

# 运行策略
hummingbot
```

### 2. 测试集成到我们的平台

```bash
# 创建测试用户
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "password123"
  }'

# 创建租户
curl -X POST http://localhost:8000/tenants/provision \
  -H "Authorization: Bearer <token>"

# 创建 Bot
curl -X POST http://localhost:8000/bots \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_name": "Test Grid Bot",
    "exchange_connection_id": "<exchange_id>",
    "strategy_template": "grid",
    "strategy_config": {
      "lower_bound": 30000,
      "upper_bound": 35000,
      "grid_count": 10,
      "order_amount": 100
    },
    "trading_pair": "BTC-USDT"
  }'

# 启动 Bot
curl -X POST http://localhost:8000/bots/<bot_id>/start \
  -H "Authorization: Bearer <token>"
```

---

## ⚠️ 重要提示

1. **Hummingbot 版本兼容性**：定期更新 Docker 镜像版本
2. **交易所支持**：确认目标交易所在 Hummingbot 支持列表中
3. **资源限制**：Hummingbot 内存占用约 512MB-1GB
4. **网络延迟**：交易策略对网络延迟敏感，建议服务器靠近交易所
5. **合规要求**：确保遵守各交易所 API 使用规则

---

**现在你可以开始集成 Hummingbot 了！** 🚀
