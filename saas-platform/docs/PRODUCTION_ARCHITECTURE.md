# 🏗️ 生产环境架构 - 1000 用户方案

## 📊 容量规划

### 用户分布假设

基于典型 SaaS 用户分布（二八定律）：

| 套餐 | 用户数 | 占比 | 每用户 Bot 数 | 总 Bot 数 | 资源需求 |
|------|--------|------|--------------|----------|----------|
| Free | 600 | 60% | 1 | 600 | 低 |
| Basic | 250 | 25% | 3 | 750 | 中 |
| Pro | 120 | 12% | 10 | 1,200 | 高 |
| Premium | 30 | 3% | 50 | 1,500 | 很高 |
| **总计** | **1,000** | **100%** | - | **4,050** | - |

### 资源计算

#### 单个 Bot 资源需求
- **CPU**: 0.1-0.2 核心
- **内存**: 256-512 MB
- **磁盘**: 500 MB（日志 + 数据）
- **网络**: 1-5 Mbps

#### 单个客户栈资源需求
```
PostgreSQL:    CPU 0.2核 + 256MB 内存
Redis:         CPU 0.1核 + 128MB 内存
Hummingbot:    CPU 0.4核 + 512MB 内存（按平均 Bot 数计算）
Dashboard:     CPU 0.15核 + 256MB 内存
监控:          CPU 0.05核 + 64MB 内存
---------------------------------------------------
总计（平均）:   CPU 0.9核 + 1.2GB 内存
```

#### 总资源需求（1000 用户）

**方式 1：全部活跃（最坏情况）**
- CPU: 900 核心
- 内存: 1.2 TB
- 磁盘: 2 TB（数据） + 5 TB（日志/备份）
- 网络带宽: 10 Gbps

**方式 2：实际使用（20% 活跃率）**
- CPU: 180 核心
- 内存: 240 GB
- 磁盘: 500 GB（数据） + 2 TB（日志/备份）
- 网络带宽: 2 Gbps

---

## 🏢 服务器架构方案

### 方案 A：单机密集部署（小规模，< 200 用户）

**配置**：1 台高配服务器

```
CPU: 64 核（AMD EPYC 或 Intel Xeon）
内存: 256 GB
磁盘: 2 x 2TB NVMe SSD（RAID 1）
网络: 10 Gbps
```

**成本**：$500-800/月（AWS c6a.16xlarge 或专用服务器）

**优点**：
- 简单易管理
- 低延迟
- 成本可控

**缺点**：
- 单点故障
- 扩展性有限
- 资源竞争风险

---

### 方案 B：多机集群（推荐，200-1000 用户）

#### 架构图

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │   (Traefik)     │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐        ┌────▼─────┐        ┌────▼─────┐
   │ Portal   │        │  Worker  │        │  Worker  │
   │ Server   │        │  Node 1  │        │  Node 2  │
   └──────────┘        └──────────┘        └──────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐        ┌────▼─────┐        ┌────▼─────┐
   │ Database │        │  Redis   │        │  Object  │
   │ Master   │        │  Cluster │        │  Storage │
   └──┬───────┘        └──────────┘        └──────────┘
      │
   ┌──▼───────┐
   │ Database │
   │ Replica  │
   └──────────┘
```

#### 服务器配置

**1. Portal 服务器（1 台）**
```
角色: 控制面 API、用户管理、编排器
CPU: 16 核
内存: 64 GB
磁盘: 500 GB SSD
成本: $150-200/月
```

**2. Worker 节点（3-5 台）**
```
角色: 运行客户栈（Hummingbot 实例）
CPU: 32 核
内存: 128 GB
磁盘: 1 TB NVMe SSD
成本: $300-400/月 x 5 = $1,500-2,000/月
```

**3. 数据库服务器（1 主 + 1 从）**
```
角色: Portal 数据库（主从复制）
CPU: 16 核
内存: 64 GB
磁盘: 1 TB NVMe SSD（RAID 1）
成本: $200/月 x 2 = $400/月
```

**4. 缓存/队列服务器（1 台）**
```
角色: Redis Cluster（缓存 + Celery 队列）
CPU: 8 核
内存: 32 GB
磁盘: 200 GB SSD
成本: $100/月
```

**5. 对象存储**
```
角色: 备份、日志归档
服务: AWS S3 / MinIO 自建
成本: $50-100/月（1 TB 存储 + 流量）
```

**总成本**：约 **$2,200-2,800/月**（自建）或 **$3,500-4,500/月**（云服务）

---

### 方案 C：云原生 Kubernetes（高可用，> 1000 用户）

#### 架构

```
K8s Cluster (EKS/GKE/AKS)
├── Portal API (Deployment, 3 replicas)
├── Worker Pool (StatefulSet, 自动扩缩容)
├── Database (RDS/CloudSQL, Multi-AZ)
├── Redis (ElastiCache/MemoryStore)
├── Object Storage (S3/GCS/Azure Blob)
└── Monitoring (Prometheus + Grafana)
```

#### 成本估算（AWS）

```
EKS 集群控制面:           $72/月
Worker 节点池:           $2,000-3,000/月（5-10 台 c6i.4xlarge）
RDS PostgreSQL:          $400/月（db.r6g.2xlarge, Multi-AZ）
ElastiCache Redis:       $200/月（cache.r6g.large）
S3 存储:                 $50-100/月
负载均衡器:              $30/月
数据传输:                $200/月
---------------------------------------------------
总计:                    $2,950-3,800/月
```

**优点**：
- 高可用（99.95%+）
- 自动扩缩容
- 容易迁移云厂商

**缺点**：
- 复杂度高
- 需要 K8s 运维经验
- 成本较高

---

## 📐 资源调度策略

### 1. 客户栈分配策略

**按套餐分层部署**：

```python
# 资源分配规则
tier_allocation = {
    "free": {
        "cpu_limit": 0.5,
        "memory_mb": 512,
        "priority": "low",
        "node_selector": "worker-low"
    },
    "basic": {
        "cpu_limit": 1.0,
        "memory_mb": 1024,
        "priority": "medium",
        "node_selector": "worker-mid"
    },
    "pro": {
        "cpu_limit": 2.0,
        "memory_mb": 2048,
        "priority": "high",
        "node_selector": "worker-high"
    },
    "premium": {
        "cpu_limit": 4.0,
        "memory_mb": 4096,
        "priority": "critical",
        "node_selector": "worker-premium"  # 专用节点
    }
}
```

### 2. 休眠机制（降低成本）

**自动休眠策略**：

```
闲置 7 天 → 自动停止所有 Bot
闲置 14 天 → 停止 Dashboard 和 Redis
闲置 30 天 → 仅保留数据库（最小资源）

唤醒：用户登录时自动启动（2-3 分钟）
```

**成本节省**：
- 休眠率 40% → 节省 30-40% 资源成本
- Free 用户强制休眠 → 节省 50% 成本

### 3. Worker 节点负载均衡

**调度算法**：

```python
def select_worker_node(tenant_tier):
    """选择最合适的 Worker 节点"""

    # 获取所有节点
    nodes = get_worker_nodes()

    # 过滤出符合套餐要求的节点
    eligible_nodes = [
        n for n in nodes
        if n.tier_support >= tenant_tier
    ]

    # 按负载排序（CPU、内存、租户数综合评分）
    sorted_nodes = sorted(
        eligible_nodes,
        key=lambda n: calculate_load_score(n)
    )

    # 返回负载最低的节点
    return sorted_nodes[0]

def calculate_load_score(node):
    """计算节点负载分数（越低越好）"""
    cpu_weight = 0.4
    memory_weight = 0.4
    tenant_weight = 0.2

    cpu_usage = node.cpu_used / node.cpu_total
    mem_usage = node.memory_used / node.memory_total
    tenant_density = node.tenant_count / node.max_tenants

    return (
        cpu_usage * cpu_weight +
        mem_usage * memory_weight +
        tenant_density * tenant_weight
    )
```

---

## 🔧 生产环境配置

### 1. 数据库优化

**PostgreSQL 配置**（64GB 内存服务器）：

```ini
# postgresql.conf

# 内存配置
shared_buffers = 16GB              # 25% 内存
effective_cache_size = 48GB        # 75% 内存
maintenance_work_mem = 2GB
work_mem = 128MB

# 连接配置
max_connections = 500
max_prepared_transactions = 200

# WAL 配置（写性能）
wal_buffers = 16MB
checkpoint_completion_target = 0.9
max_wal_size = 4GB

# 查询优化
random_page_cost = 1.1            # SSD
effective_io_concurrency = 200
default_statistics_target = 100

# 日志配置
log_min_duration_statement = 1000  # 记录慢查询（> 1s）
log_checkpoints = on
log_connections = on
log_disconnections = on
```

**索引优化**：

```sql
-- 高频查询索引
CREATE INDEX CONCURRENTLY idx_tenants_user_status ON tenants(user_id, status) INCLUDE (tenant_code);
CREATE INDEX CONCURRENTLY idx_bots_tenant_status ON bots(tenant_id, status) INCLUDE (bot_name);
CREATE INDEX CONCURRENTLY idx_alerts_user_created ON alerts(user_id, created_at DESC) WHERE is_acknowledged = false;

-- 分区表（按月分区告警表）
CREATE TABLE alerts_202401 PARTITION OF alerts
FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### 2. Redis 配置

**Redis Cluster 模式**（3 主 3 从）：

```ini
# redis.conf

# 内存配置
maxmemory 8gb
maxmemory-policy allkeys-lru

# 持久化（根据需求选择）
save 900 1
save 300 10
save 60 10000

# Cluster 配置
cluster-enabled yes
cluster-node-timeout 5000
cluster-require-full-coverage no

# 性能优化
io-threads 4
io-threads-do-reads yes
```

### 3. Docker 优化

**daemon.json**：

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ],
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  },
  "default-shm-size": "128M",
  "live-restore": true
}
```

---

## 📊 监控方案

### 1. 指标收集

**Prometheus 配置**：

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Portal API
  - job_name: 'portal-api'
    static_configs:
      - targets: ['portal-api:8000']

  # Worker 节点
  - job_name: 'worker-nodes'
    static_configs:
      - targets:
        - 'worker-1:9100'
        - 'worker-2:9100'
        - 'worker-3:9100'

  # 租户容器（动态发现）
  - job_name: 'tenant-containers'
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
    relabel_configs:
      - source_labels: [__meta_docker_container_label_tenant_code]
        target_label: tenant
```

### 2. 告警规则

```yaml
# alerts.yml
groups:
  - name: system
    rules:
      # 节点 CPU 过高
      - alert: HighCPUUsage
        expr: node_cpu_usage > 0.85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "节点 CPU 使用率超过 85%"

      # 节点内存过高
      - alert: HighMemoryUsage
        expr: node_memory_usage > 0.90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "节点内存使用率超过 90%"

      # 容器重启频繁
      - alert: ContainerRestarting
        expr: rate(docker_container_restarts[5m]) > 3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "容器频繁重启"

  - name: application
    rules:
      # API 响应慢
      - alert: SlowAPIResponse
        expr: http_request_duration_seconds{quantile="0.95"} > 2
        for: 5m
        labels:
          severity: warning

      # 租户创建失败率高
      - alert: HighTenantProvisionFailureRate
        expr: rate(tenant_provision_failures[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
```

### 3. Grafana Dashboard

**关键面板**：

1. **总览**
   - 总用户数
   - 活跃租户数
   - 运行中的 Bot 数
   - API QPS
   - 错误率

2. **资源使用**
   - 各节点 CPU/内存使用率
   - 磁盘 I/O
   - 网络流量
   - 容器数量

3. **业务指标**
   - 新增用户（按天）
   - 订阅转化率
   - Bot 创建/启动数
   - 告警数量（按类型）

4. **成本分析**
   - 各套餐资源消耗
   - 休眠率
   - 节点利用率

---

## 🔒 安全加固

### 1. 网络隔离

```
┌─────────────────────────────────────┐
│         Public Internet             │
└──────────────┬──────────────────────┘
               │
        ┌──────▼──────┐
        │   Firewall  │
        │  (只开 80/443) │
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │   Traefik   │
        │ (反向代理)   │
        └──────┬──────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐  ┌──▼───┐  ┌──▼───┐
│Portal │  │Worker│  │Worker│
│(DMZ)  │  │(内网) │  │(内网) │
└───┬───┘  └──────┘  └──────┘
    │
┌───▼───────────┐
│  Database     │
│  (内网, VPC)  │
└───────────────┘
```

### 2. 客户栈隔离

- **网络隔离**：每个租户独立 Docker Network
- **资源隔离**：CPU/Memory Limits + Reservations
- **存储隔离**：独立目录，禁止跨租户访问
- **进程隔离**：不同 User Namespace

### 3. 定期安全审计

```bash
# 每周执行
- 检查未授权访问日志
- 扫描容器镜像漏洞
- 审查权限变更
- 检查异常流量

# 每月执行
- 更新系统补丁
- 轮换密钥（JWT Secret、Encryption Key）
- 审查用户行为异常
- 第三方安全扫描
```

---

## 📈 扩容策略

### 水平扩容触发条件

```
CPU 平均使用率 > 70%（持续 10 分钟）
→ 添加 1 台 Worker 节点

内存平均使用率 > 80%（持续 10 分钟）
→ 添加 1 台 Worker 节点

租户数 > 节点容量 * 0.8
→ 添加 1 台 Worker 节点
```

### 自动扩容脚本

```python
def auto_scale():
    """自动扩容决策"""
    metrics = get_cluster_metrics()

    if should_scale_up(metrics):
        # 云环境：调用 API 创建新实例
        new_node = provision_worker_node()
        register_node(new_node)

    elif should_scale_down(metrics):
        # 低峰期缩容
        if can_safely_remove_node():
            drain_node(least_loaded_node)
            terminate_node(least_loaded_node)
```

---

## 💰 成本优化建议

### 1. 使用 Spot 实例（云环境）

- Worker 节点使用 Spot/Preemptible 实例
- 节省 60-80% 成本
- 需要实现自动迁移机制

### 2. 休眠策略

```
Free 用户: 强制 7 天休眠
Basic: 14 天自动休眠
Pro: 30 天提示休眠
Premium: 不休眠
```

### 3. 资源复用

- 共享 Redis（按 schema 隔离）
- 共享 PostgreSQL（小用户）
- 延迟加载（按需启动）

### 4. 成本监控

```sql
-- 每个租户的资源成本
SELECT
    t.tenant_code,
    s.tier,
    SUM(cpu_usage) * 0.05 as cpu_cost,    -- $0.05/core-hour
    SUM(memory_mb) / 1024 * 0.01 as memory_cost,  -- $0.01/GB-hour
    COUNT(b.id) * 0.001 as bot_cost       -- $0.001/bot-hour
FROM tenants t
JOIN subscriptions s ON t.subscription_id = s.id
LEFT JOIN bots b ON b.tenant_id = t.id
GROUP BY t.tenant_code, s.tier
ORDER BY (cpu_cost + memory_cost + bot_cost) DESC;
```

---

## 🎯 1000 用户推荐配置

### 最优方案（性价比）

**方案 B（多机集群）+ 休眠机制**

```
Portal 服务器:     1 x 16 核 64GB
Worker 节点:      5 x 32 核 128GB
数据库:           1 x 16 核 64GB (主) + 1 x 8 核 32GB (从)
Redis:            1 x 8 核 32GB
对象存储:         1 TB (S3 或 MinIO)
---------------------------------------------------
月成本:          $2,500-3,200

实际容量:        1,500-2,000 用户（包含休眠）
活跃用户:        600-800（同时活跃）
```

### 启动顺序

```bash
# 1. 启动基础设施
docker compose -f infra.yml up -d  # DB, Redis, MinIO

# 2. 启动 Portal
docker compose -f portal.yml up -d

# 3. 启动 Worker 节点
# 在每台 Worker 上执行
docker compose -f worker.yml up -d

# 4. 启动监控
docker compose -f monitoring.yml up -d
```

---

## 📚 相关文档

- [部署指南](DEPLOYMENT.md)
- [Hummingbot 集成](HUMMINGBOT_INTEGRATION.md)
- [监控配置](MONITORING.md)
- [故障排查](TROUBLESHOOTING.md)
