"""
Hummingbot SaaS Platform - Database Models
完整的数据库表结构设计
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


# ==================== 枚举类型 ====================

class SubscriptionTier(str, Enum):
    """订阅套餐"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    PREMIUM = "premium"


class SubscriptionStatus(str, Enum):
    """订阅状态"""
    ACTIVE = "active"
    TRIAL = "trial"
    GRACE_PERIOD = "grace_period"  # 宽限期
    SUSPENDED = "suspended"
    CANCELED = "canceled"


class TenantStatus(str, Enum):
    """客户栈状态"""
    PROVISIONING = "provisioning"  # 正在创建
    RUNNING = "running"
    STOPPED = "stopped"
    HIBERNATING = "hibernating"  # 休眠
    ERROR = "error"
    TERMINATED = "terminated"


class BotStatus(str, Enum):
    """Bot 状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class StrategyTemplate(str, Enum):
    """策略模板"""
    GRID = "grid"
    DCA = "dca"
    SIGNAL_WEBHOOK = "signal_webhook"
    CUSTOM = "custom"


class AlertSeverity(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    """工单状态"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ==================== 核心表 ====================

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # 用户信息
    full_name = Column(String(255))
    phone = Column(String(50))
    country = Column(String(100))
    timezone = Column(String(50), default="UTC")

    # 账户状态
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime)

    # 通知设置
    notification_email = Column(Boolean, default=True)
    notification_telegram = Column(Boolean, default=False)
    telegram_chat_id = Column(String(255))

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime)

    # 关联
    subscriptions = relationship("Subscription", back_populates="user")
    tenants = relationship("Tenant", back_populates="user")
    tickets = relationship("Ticket", back_populates="user")


class Subscription(Base):
    """订阅表"""
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # 套餐信息
    tier = Column(SQLEnum(SubscriptionTier), nullable=False)
    status = Column(SQLEnum(SubscriptionStatus), nullable=False)

    # 配额
    max_bots = Column(Integer, default=1)
    max_exchanges = Column(Integer, default=2)
    log_retention_days = Column(Integer, default=7)
    backup_retention_days = Column(Integer, default=7)
    enable_webhooks = Column(Boolean, default=False)
    enable_advanced_strategies = Column(Boolean, default=False)
    enable_api_access = Column(Boolean, default=False)

    # 资源限制
    cpu_limit = Column(Float, default=1.0)  # CPU 核心数
    memory_limit_mb = Column(Integer, default=512)  # 内存 MB

    # 计费
    price_monthly = Column(Float)
    currency = Column(String(10), default="USD")
    billing_cycle_start = Column(DateTime)
    billing_cycle_end = Column(DateTime)
    next_billing_date = Column(DateTime)

    # 支付信息
    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255))
    payment_method = Column(String(50))

    # 试用期
    trial_ends_at = Column(DateTime)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    canceled_at = Column(DateTime)

    # 关联
    user = relationship("User", back_populates="subscriptions")

    # 索引
    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
    )


class Tenant(Base):
    """客户栈表 - 每个客户的独立运行环境"""
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"))

    # 租户信息
    tenant_code = Column(String(50), unique=True, nullable=False, index=True)  # 如 u123
    display_name = Column(String(255))

    # 域名与访问
    subdomain = Column(String(255), unique=True, nullable=False)  # u123.yourdomain.com
    api_subdomain = Column(String(255), unique=True)  # api-u123.yourdomain.com
    dashboard_url = Column(String(500))
    api_url = Column(String(500))

    # 部署信息
    status = Column(SQLEnum(TenantStatus), nullable=False, default=TenantStatus.PROVISIONING)
    host_machine = Column(String(255))  # 宿主机标识
    deployment_path = Column(String(500))  # /srv/tenants/u123

    # 版本与配置
    hummingbot_version = Column(String(50))
    dashboard_version = Column(String(50))
    compose_file_path = Column(String(500))

    # 健康状态
    last_health_check = Column(DateTime)
    health_status = Column(String(50))  # healthy, degraded, unhealthy
    cpu_usage_percent = Column(Float)
    memory_usage_mb = Column(Integer)

    # 运行统计
    uptime_seconds = Column(Integer, default=0)
    restart_count = Column(Integer, default=0)
    last_restart_at = Column(DateTime)

    # 休眠管理
    hibernate_after_days = Column(Integer, default=7)
    last_activity_at = Column(DateTime)
    hibernated_at = Column(DateTime)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    terminated_at = Column(DateTime)

    # 关联
    user = relationship("User", back_populates="tenants")
    bots = relationship("Bot", back_populates="tenant")
    alerts = relationship("Alert", back_populates="tenant")
    backups = relationship("Backup", back_populates="tenant")

    # 索引
    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_host_status", "host_machine", "status"),
    )


class ExchangeConnection(Base):
    """交易所连接表 - 存储加密的 API Keys"""
    __tablename__ = "exchange_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    # 交易所信息
    exchange_name = Column(String(100), nullable=False)  # binance, okx, etc.
    connection_name = Column(String(255))  # 用户自定义名称

    # 加密的凭证（关键）
    encrypted_api_key = Column(Text, nullable=False)
    encrypted_api_secret = Column(Text, nullable=False)
    encrypted_passphrase = Column(Text)  # OKX 等需要
    encryption_key_version = Column(String(50), default="v1")  # 密钥版本，便于轮换

    # 权限检查
    permissions = Column(JSON)  # {"spot": true, "futures": false, "withdraw": false}
    last_permission_check = Column(DateTime)

    # 连接状态
    is_active = Column(Boolean, default=True)
    last_connection_test = Column(DateTime)
    connection_test_success = Column(Boolean)
    connection_error = Column(Text)

    # Rate Limit 管理
    rate_limit_used = Column(Integer, default=0)
    rate_limit_max = Column(Integer)
    rate_limit_reset_at = Column(DateTime)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    bots = relationship("Bot", back_populates="exchange_connection")

    # 索引
    __table_args__ = (
        Index("idx_tenant_exchange", "tenant_id", "exchange_name"),
        UniqueConstraint("user_id", "connection_name", name="uq_user_connection_name"),
    )


class Bot(Base):
    """Bot 实例表"""
    __tablename__ = "bots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    exchange_connection_id = Column(String(36), ForeignKey("exchange_connections.id"))

    # Bot 信息
    bot_name = Column(String(255), nullable=False)
    description = Column(Text)

    # 策略配置
    strategy_template = Column(SQLEnum(StrategyTemplate), nullable=False)
    strategy_config = Column(JSON, nullable=False)  # 策略参数（JSON）

    # 交易对与市场
    trading_pair = Column(String(50))  # BTC-USDT
    market_type = Column(String(50))  # spot, futures

    # 运行状态
    status = Column(SQLEnum(BotStatus), nullable=False, default=BotStatus.STOPPED)
    container_id = Column(String(255))  # Docker 容器 ID
    process_id = Column(String(255))  # Hummingbot 进程 ID

    # 风控设置
    risk_config = Column(JSON)  # {"max_position": 1000, "max_loss_daily": 50, "stop_loss": 5}
    circuit_breaker_enabled = Column(Boolean, default=True)
    circuit_breaker_triggered = Column(Boolean, default=False)

    # 性能统计
    total_pnl = Column(Float, default=0.0)
    total_pnl_percent = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)

    # 运行时间
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    running_time_seconds = Column(Integer, default=0)

    # 错误信息
    last_error = Column(Text)
    error_count = Column(Integer, default=0)
    last_error_at = Column(DateTime)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    tenant = relationship("Tenant", back_populates="bots")
    exchange_connection = relationship("ExchangeConnection", back_populates="bots")
    alerts = relationship("Alert", back_populates="bot")

    # 索引
    __table_args__ = (
        Index("idx_tenant_status", "tenant_id", "status"),
        Index("idx_user_status", "user_id", "status"),
    )


class Alert(Base):
    """告警记录表"""
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"))
    bot_id = Column(String(36), ForeignKey("bots.id"))

    # 告警信息
    severity = Column(SQLEnum(AlertSeverity), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    alert_type = Column(String(100))  # bot_stopped, exchange_disconnected, order_failed, etc.

    # 上下文
    metadata = Column(JSON)  # 额外信息

    # 通知状态
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime)
    notification_channels = Column(JSON)  # ["email", "telegram"]

    # 去重（5分钟内同类告警只发一次）
    dedup_key = Column(String(255), index=True)  # 用于去重

    # 确认状态
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(36))

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关联
    tenant = relationship("Tenant", back_populates="alerts")
    bot = relationship("Bot", back_populates="alerts")

    # 索引
    __table_args__ = (
        Index("idx_user_severity_created", "user_id", "severity", "created_at"),
        Index("idx_dedup_created", "dedup_key", "created_at"),
    )


class Webhook(Base):
    """Webhook 配置表（用于 Signal 策略）"""
    __tablename__ = "webhooks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    bot_id = Column(String(36), ForeignKey("bots.id"), nullable=False)

    # Webhook 信息
    webhook_url = Column(String(500), unique=True, nullable=False)
    webhook_secret = Column(String(255), nullable=False)  # 用于验证请求

    # 配置
    is_active = Column(Boolean, default=True)
    allowed_ips = Column(JSON)  # IP 白名单

    # 统计
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    last_request_at = Column(DateTime)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Backup(Base):
    """备份记录表"""
    __tablename__ = "backups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    # 备份信息
    backup_type = Column(String(50))  # full, incremental, config_only
    backup_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)

    # 备份内容
    includes_database = Column(Boolean, default=True)
    includes_configs = Column(Boolean, default=True)
    includes_logs = Column(Boolean, default=False)

    # 状态
    status = Column(String(50))  # pending, running, completed, failed
    error_message = Column(Text)

    # 时间
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    expires_at = Column(DateTime)  # 根据套餐保留天数

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关联
    tenant = relationship("Tenant", back_populates="backups")

    # 索引
    __table_args__ = (
        Index("idx_tenant_created", "tenant_id", "created_at"),
    )


class Ticket(Base):
    """工单表"""
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # 工单信息
    ticket_number = Column(String(50), unique=True, nullable=False)  # TK-20260116-001
    subject = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    # 分类
    category = Column(String(100))  # technical, billing, feature_request, bug
    priority = Column(String(50))  # low, medium, high, urgent

    # 状态
    status = Column(SQLEnum(TicketStatus), nullable=False, default=TicketStatus.OPEN)

    # 处理信息
    assigned_to = Column(String(36))  # 客服/技术人员 ID

    # 时间
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime)
    closed_at = Column(DateTime)

    # SLA
    sla_response_deadline = Column(DateTime)  # 首次响应截止时间
    sla_resolution_deadline = Column(DateTime)  # 解决截止时间
    first_response_at = Column(DateTime)

    # 关联
    user = relationship("User", back_populates="tickets")
    messages = relationship("TicketMessage", back_populates="ticket")

    # 索引
    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_assigned_status", "assigned_to", "status"),
    )


class TicketMessage(Base):
    """工单消息表"""
    __tablename__ = "ticket_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False)

    # 消息信息
    sender_id = Column(String(36), nullable=False)  # 用户或客服 ID
    sender_type = Column(String(50))  # user, staff
    message = Column(Text, nullable=False)

    # 附件
    attachments = Column(JSON)  # [{"filename": "...", "url": "..."}]

    # 是否内部备注
    is_internal = Column(Boolean, default=False)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关联
    ticket = relationship("Ticket", back_populates="messages")


class AuditLog(Base):
    """审计日志表（重要操作记录）"""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # 操作主体
    user_id = Column(String(36), index=True)
    tenant_id = Column(String(36), index=True)

    # 操作信息
    action = Column(String(255), nullable=False)  # create_bot, delete_bot, update_api_key, etc.
    resource_type = Column(String(100))  # bot, tenant, exchange_connection
    resource_id = Column(String(36))

    # 详情
    details = Column(JSON)  # 操作详细参数
    ip_address = Column(String(100))
    user_agent = Column(String(500))

    # 结果
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 索引
    __table_args__ = (
        Index("idx_user_action_created", "user_id", "action", "created_at"),
        Index("idx_tenant_action_created", "tenant_id", "action", "created_at"),
    )


# ==================== 系统表 ====================

class HostMachine(Base):
    """宿主机表（用于资源调度）"""
    __tablename__ = "host_machines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # 机器信息
    hostname = Column(String(255), unique=True, nullable=False)
    ip_address = Column(String(100))
    region = Column(String(100))  # us-east-1, ap-southeast-1

    # 资源容量
    total_cpu_cores = Column(Float)
    total_memory_mb = Column(Integer)
    total_disk_gb = Column(Integer)

    # 已分配资源
    allocated_cpu = Column(Float, default=0)
    allocated_memory_mb = Column(Integer, default=0)
    allocated_disk_gb = Column(Integer, default=0)

    # 运行统计
    tenant_count = Column(Integer, default=0)

    # 状态
    is_active = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime)

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemConfig(Base):
    """系统配置表（Key-Value 存储）"""
    __tablename__ = "system_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # 配置项
    config_key = Column(String(255), unique=True, nullable=False)
    config_value = Column(Text)
    config_type = Column(String(50))  # string, int, float, json, bool

    # 描述
    description = Column(Text)
    is_secret = Column(Boolean, default=False)  # 是否敏感信息

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
