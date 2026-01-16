"""
API Schemas (Pydantic Models)
用于请求验证和响应序列化
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

# 从数据库模型导入枚举
from database.models import (
    SubscriptionTier, SubscriptionStatus, TenantStatus,
    BotStatus, StrategyTemplate, AlertSeverity, TicketStatus
)


# ==================== 用户相关 ====================

class UserCreate(BaseModel):
    """用户注册"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

    @validator('username')
    def username_alphanumeric(cls, v):
        assert v.isalnum(), 'must be alphanumeric'
        return v


class LoginRequest(BaseModel):
    """登录请求"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """用户响应"""
    id: str
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== 订阅相关 ====================

class SubscriptionResponse(BaseModel):
    """订阅响应"""
    id: str
    tier: SubscriptionTier
    status: SubscriptionStatus
    max_bots: int
    max_exchanges: int
    log_retention_days: int
    backup_retention_days: int
    enable_webhooks: bool
    enable_advanced_strategies: bool
    price_monthly: Optional[float]
    billing_cycle_end: Optional[datetime]
    trial_ends_at: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


class SubscriptionUpgrade(BaseModel):
    """订阅升级请求"""
    new_tier: SubscriptionTier
    payment_method_id: Optional[str] = None  # Stripe payment method


# ==================== 租户相关 ====================

class TenantResponse(BaseModel):
    """租户响应"""
    id: str
    tenant_code: str
    subdomain: str
    dashboard_url: str
    api_url: str
    status: TenantStatus
    hummingbot_version: Optional[str]
    health_status: Optional[str]
    cpu_usage_percent: Optional[float]
    memory_usage_mb: Optional[int]
    uptime_seconds: int
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== 交易所连接相关 ====================

class ExchangeConnectionCreate(BaseModel):
    """创建交易所连接"""
    exchange_name: str = Field(..., description="Exchange name (e.g., binance, okx)")
    connection_name: str = Field(..., description="User-defined connection name")
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None  # For OKX, etc.


class ExchangeConnectionUpdate(BaseModel):
    """更新交易所连接"""
    connection_name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    is_active: Optional[bool] = None


class ExchangeConnectionResponse(BaseModel):
    """交易所连接响应（不返回密钥）"""
    id: str
    exchange_name: str
    connection_name: str
    is_active: bool
    last_connection_test: Optional[datetime]
    connection_test_success: Optional[bool]
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== Bot 相关 ====================

class BotCreate(BaseModel):
    """创建 Bot"""
    bot_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    exchange_connection_id: str
    strategy_template: StrategyTemplate
    strategy_config: Dict[str, Any] = Field(
        ...,
        description="Strategy parameters (JSON)"
    )
    trading_pair: str = Field(..., description="Trading pair (e.g., BTC-USDT)")
    market_type: str = Field(default="spot", description="Market type (spot/futures)")
    risk_config: Optional[Dict[str, Any]] = Field(
        default={
            "max_position_usd": 1000,
            "max_loss_daily_usd": 100,
            "circuit_breaker_enabled": True,
        }
    )

    @validator('strategy_config')
    def validate_strategy_config(cls, v, values):
        """验证策略配置"""
        if 'strategy_template' not in values:
            return v

        template = values['strategy_template']

        # Grid 策略必需参数
        if template == StrategyTemplate.GRID:
            required = ['lower_bound', 'upper_bound', 'grid_count', 'order_amount']
            missing = [k for k in required if k not in v]
            if missing:
                raise ValueError(f"Grid strategy missing parameters: {missing}")

        # DCA 策略必需参数
        elif template == StrategyTemplate.DCA:
            required = ['order_amount', 'order_interval_seconds', 'max_orders']
            missing = [k for k in required if k not in v]
            if missing:
                raise ValueError(f"DCA strategy missing parameters: {missing}")

        return v


class BotUpdate(BaseModel):
    """更新 Bot"""
    bot_name: Optional[str] = None
    description: Optional[str] = None
    strategy_config: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None


class BotResponse(BaseModel):
    """Bot 响应"""
    id: str
    bot_name: str
    description: Optional[str]
    strategy_template: StrategyTemplate
    strategy_config: Dict[str, Any]
    trading_pair: str
    market_type: str
    status: BotStatus
    total_pnl: float
    total_pnl_percent: float
    total_trades: int
    win_rate: float
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    running_time_seconds: int
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== 告警相关 ====================

class AlertResponse(BaseModel):
    """告警响应"""
    id: str
    severity: AlertSeverity
    title: str
    message: str
    alert_type: str
    metadata: Optional[Dict[str, Any]]
    is_acknowledged: bool
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== 工单相关 ====================

class TicketCreate(BaseModel):
    """创建工单"""
    subject: str = Field(..., min_length=5, max_length=500)
    description: str = Field(..., min_length=20)
    category: Optional[str] = Field(default="technical")
    priority: Optional[str] = Field(default="medium")


class TicketMessageCreate(BaseModel):
    """工单消息"""
    message: str = Field(..., min_length=1)


class TicketResponse(BaseModel):
    """工单响应"""
    id: str
    ticket_number: str
    subject: str
    description: str
    category: str
    priority: str
    status: TicketStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== Webhook 相关 ====================

class WebhookCreate(BaseModel):
    """创建 Webhook"""
    bot_id: str


class WebhookResponse(BaseModel):
    """Webhook 响应"""
    id: str
    webhook_url: str
    webhook_secret: str
    is_active: bool
    total_requests: int
    successful_requests: int
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


class WebhookSignalPayload(BaseModel):
    """Webhook 信号负载（TradingView 等）"""
    action: str = Field(..., description="Action: buy, sell, close")
    symbol: str = Field(..., description="Trading pair")
    price: Optional[float] = None
    quantity: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


# ==================== 备份相关 ====================

class BackupResponse(BaseModel):
    """备份响应"""
    id: str
    backup_type: str
    file_size_bytes: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        orm_mode = True
        from_attributes = True


# ==================== 统计相关 ====================

class DashboardStats(BaseModel):
    """仪表盘统计"""
    total_bots: int
    running_bots: int
    stopped_bots: int
    total_pnl: float
    total_trades: int
    active_alerts: int
    tenant_status: str
    subscription_tier: str
    subscription_expires_at: Optional[datetime]
