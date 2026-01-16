# 🚀 快速部署指南

本文档提供 Hummingbot SaaS 平台的完整部署流程。

---

## 📋 前置要求

### 硬件要求
- **最小配置**（测试环境）：
  - 2 核 CPU
  - 4GB RAM
  - 40GB 硬盘

- **推荐配置**（生产环境，10-50 用户）：
  - 4 核 CPU
  - 16GB RAM
  - 200GB SSD

- **扩展配置**（100+ 用户）：
  - 8+ 核 CPU
  - 32GB+ RAM
  - 500GB+ SSD
  - 多台宿主机（负载均衡）

### 软件要求
- Ubuntu 22.04 LTS（推荐）
- Docker 24.0+
- Docker Compose 2.20+
- PostgreSQL 15+
- Python 3.10+

### 域名与 DNS
- 主域名：`yourdomain.com`
- Portal API：`api.yourdomain.com`
- 泛域名解析：`*.yourdomain.com` → 服务器 IP

---

## 🛠️ 部署步骤

### 1. 服务器准备

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装 Docker Compose
sudo apt install docker-compose-plugin -y

# 安装其他依赖
sudo apt install -y git python3-pip postgresql-client redis-tools

# 验证安装
docker --version
docker compose version
```

### 2. 克隆项目

```bash
cd /opt
sudo git clone https://github.com/yourusername/hummingbot-saas.git
cd hummingbot-saas
sudo chown -R $USER:$USER .
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 生成密钥
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env
python3 -c "import secrets, base64; print('ENCRYPTION_MASTER_KEY=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" >> .env

# 编辑配置
nano .env
```

**必须修改的配置项：**

```bash
# 数据库
DATABASE_URL=postgresql://postgres:YOUR_SECURE_PASSWORD@localhost:5432/hummingbot_saas

# 邮件（使用 Gmail 示例）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password  # 不是邮箱密码！需要在 Google 账户设置中生成
FROM_EMAIL=noreply@yourdomain.com

# Telegram（可选）
TELEGRAM_BOT_TOKEN=your-bot-token  # 从 @BotFather 获取

# 域名
BASE_DOMAIN=yourdomain.com
PORTAL_URL=https://api.yourdomain.com

# 管理员
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=change_me_after_first_login
```

### 4. 安装 Python 依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. 初始化数据库

```bash
# 创建 PostgreSQL 数据库
sudo -u postgres psql -c "CREATE DATABASE hummingbot_saas;"
sudo -u postgres psql -c "CREATE USER hummingbot WITH ENCRYPTED PASSWORD 'your-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE hummingbot_saas TO hummingbot;"

# 初始化系统
python3 scripts/init_system.py
```

### 6. 配置 Traefik（反向代理 + 自动 HTTPS）

```bash
# 创建 Traefik 配置目录
mkdir -p traefik
cd traefik

# 创建配置文件
cat > traefik.yml <<EOF
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
    watch: true

api:
  dashboard: true
  insecure: true

log:
  level: INFO
EOF

# 创建 acme.json（存储 SSL 证书）
touch acme.json
chmod 600 acme.json

# 创建 Docker 网络
docker network create web
```

### 7. 启动服务

#### 方式 1：使用 Docker Compose（推荐）

```bash
# 返回项目根目录
cd /opt/hummingbot-saas

# 启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f
```

#### 方式 2：直接运行（开发环境）

```bash
# 启动 Portal API
source venv/bin/activate
python api/main.py
```

### 8. 配置定时任务

```bash
# 编辑 crontab
crontab -e

# 添加以下内容
# 每天凌晨 2 点备份
0 2 * * * cd /opt/hummingbot-saas && /opt/hummingbot-saas/venv/bin/python scripts/daily_backup.py >> /var/log/hummingbot-backup.log 2>&1

# 每天凌晨 3 点清理
0 3 * * * cd /opt/hummingbot-saas && /opt/hummingbot-saas/venv/bin/python scripts/cleanup_backups.py >> /var/log/hummingbot-cleanup.log 2>&1

# 每 5 分钟健康检查
*/5 * * * * cd /opt/hummingbot-saas && /opt/hummingbot-saas/venv/bin/python scripts/health_check.py >> /var/log/hummingbot-health.log 2>&1
```

### 9. 验证部署

```bash
# 检查服务状态
docker compose ps

# 测试 API
curl https://api.yourdomain.com/health

# 查看日志
docker compose logs portal-api
```

---

## 🔒 安全加固

### 1. 防火墙配置

```bash
# 启用 UFW
sudo ufw enable

# 允许 SSH
sudo ufw allow 22/tcp

# 允许 HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 查看规则
sudo ufw status
```

### 2. 限制 SSH 访问

```bash
# 编辑 SSH 配置
sudo nano /etc/ssh/sshd_config

# 修改以下配置
PermitRootLogin no
PasswordAuthentication no  # 只允许密钥登录
Port 2222  # 修改默认端口（可选）

# 重启 SSH
sudo systemctl restart sshd
```

### 3. 配置 Fail2Ban

```bash
# 安装 Fail2Ban
sudo apt install fail2ban -y

# 创建配置
sudo nano /etc/fail2ban/jail.local

# 添加
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

# 启动服务
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 📊 监控配置（可选）

### 使用 Prometheus + Grafana

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

启动：
```bash
docker compose -f docker-compose.monitoring.yml up -d
```

---

## 🔄 更新与升级

### 更新 Portal API

```bash
cd /opt/hummingbot-saas

# 拉取最新代码
git pull origin main

# 更新依赖
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 运行数据库迁移（如有）
alembic upgrade head

# 重启服务
docker compose restart portal-api
```

### 批量升级客户栈

```python
# scripts/upgrade_all_tenants.py
from database import get_db
from database.models import Tenant, TenantStatus
from core.orchestrator import TenantOrchestrator

orchestrator = TenantOrchestrator()

with get_db() as db:
    tenants = db.query(Tenant).filter(
        Tenant.status == TenantStatus.RUNNING
    ).all()

    for tenant in tenants:
        try:
            orchestrator.upgrade_tenant_stack(
                tenant.id,
                new_version="1.2.0",
                backup_first=True
            )
            print(f"✓ Upgraded: {tenant.tenant_code}")
        except Exception as e:
            print(f"✗ Failed: {tenant.tenant_code} - {e}")
```

---

## 🐛 故障排查

### 问题 1：端口已被占用

```bash
# 查找占用端口的进程
sudo lsof -i :8000

# 终止进程
sudo kill -9 <PID>
```

### 问题 2：容器无法启动

```bash
# 查看容器日志
docker compose logs <service-name>

# 进入容器排查
docker compose exec <service-name> bash

# 重建容器
docker compose down
docker compose up -d --force-recreate
```

### 问题 3：数据库连接失败

```bash
# 测试数据库连接
psql postgresql://postgres:password@localhost:5432/hummingbot_saas -c "SELECT 1"

# 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 查看 PostgreSQL 日志
sudo tail -f /var/log/postgresql/postgresql-15-main.log
```

### 问题 4：SSL 证书申请失败

```bash
# 检查域名解析
dig api.yourdomain.com

# 查看 Traefik 日志
docker compose logs traefik

# 手动申请证书
sudo certbot certonly --standalone -d api.yourdomain.com
```

---

## 📈 性能优化

### 数据库优化

```sql
-- 创建索引（如果还没有）
CREATE INDEX idx_tenants_user_status ON tenants(user_id, status);
CREATE INDEX idx_bots_tenant_status ON bots(tenant_id, status);
CREATE INDEX idx_alerts_user_created ON alerts(user_id, created_at DESC);

-- 定期 VACUUM
VACUUM ANALYZE;

-- 查看慢查询
SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;
```

### Nginx 缓存（如果使用 Nginx 代替 Traefik）

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g;

location / {
    proxy_cache api_cache;
    proxy_cache_valid 200 5m;
    proxy_cache_key "$request_uri";
    add_header X-Cache-Status $upstream_cache_status;
}
```

---

## 📞 获取帮助

- 文档：https://docs.yourdomain.com
- 社区：https://community.yourdomain.com
- 邮箱：support@yourdomain.com
- GitHub Issues：https://github.com/yourusername/hummingbot-saas/issues

---

**祝部署顺利！🎉**
