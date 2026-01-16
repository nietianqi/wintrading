"""
Hummingbot SaaS Platform - Portal API
FastAPI 主应用
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import uvicorn
from datetime import datetime

from database import get_db_session, init_database
from database.models import User, Subscription, Tenant, Bot, Alert
from api.schemas import *
from api.dependencies import get_current_user, require_active_subscription
from core.encryption import EncryptionManager

# 初始化 FastAPI
app = FastAPI(
    title="Hummingbot SaaS Platform API",
    description="托管版 Hummingbot 交易平台",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全
security = HTTPBearer()


# ==================== 健康检查 ====================

@app.get("/health")
def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "hummingbot-saas-portal",
    }


@app.get("/")
def root():
    """根路径"""
    return {
        "message": "Hummingbot SaaS Platform API",
        "docs": "/docs",
        "version": "1.0.0",
    }


# ==================== 用户管理 ====================

@app.post("/auth/register", response_model=UserResponse)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db_session)
):
    """
    用户注册

    流程：
    1. 验证邮箱唯一性
    2. 创建用户
    3. 创建默认订阅（Free 或 Trial）
    4. 返回用户信息（不包含密码）
    """
    # 检查邮箱是否已存在
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # 检查用户名是否已存在
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # 创建用户（密码哈希应使用 bcrypt 等）
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    new_user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=pwd_context.hash(user_data.password),
        full_name=user_data.full_name,
    )

    db.add(new_user)
    db.flush()  # 获取 user.id

    # 创建默认订阅（Trial 14 天）
    from datetime import timedelta
    trial_subscription = Subscription(
        user_id=new_user.id,
        tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.TRIAL,
        max_bots=1,
        max_exchanges=2,
        log_retention_days=7,
        backup_retention_days=7,
        enable_webhooks=False,
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
    )

    db.add(trial_subscription)
    db.commit()
    db.refresh(new_user)

    return UserResponse.from_orm(new_user)


@app.post("/auth/login")
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db_session)
):
    """
    用户登录

    返回 JWT Token（实际项目需要实现 JWT）
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # 查找用户
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # 验证密码
    if not pwd_context.verify(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # 更新最后登录时间
    user.last_login_at = datetime.utcnow()
    db.commit()

    # 生成 JWT Token（这里简化，实际应使用 PyJWT）
    from jose import jwt
    from datetime import timedelta
    import os

    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    access_token = jwt.encode(
        {"sub": user.id, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY,
        algorithm="HS256"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(user),
    }


@app.get("/users/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """获取当前用户信息"""
    return UserResponse.from_orm(current_user)


# ==================== 订阅管理 ====================

@app.get("/subscriptions/me", response_model=SubscriptionResponse)
def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """获取当前用户的订阅信息"""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
    ).first()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )

    return SubscriptionResponse.from_orm(subscription)


@app.post("/subscriptions/upgrade")
def upgrade_subscription(
    upgrade_data: SubscriptionUpgrade,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    升级订阅

    实际项目需要集成 Stripe 等支付
    """
    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == SubscriptionStatus.ACTIVE
    ).first()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )

    # 更新套餐（这里简化，实际需要处理支付）
    tier_config = {
        SubscriptionTier.BASIC: {
            "max_bots": 1,
            "max_exchanges": 2,
            "log_retention_days": 7,
            "backup_retention_days": 7,
            "enable_webhooks": False,
            "price_monthly": 29.0,
        },
        SubscriptionTier.PRO: {
            "max_bots": 5,
            "max_exchanges": 5,
            "log_retention_days": 30,
            "backup_retention_days": 30,
            "enable_webhooks": True,
            "price_monthly": 99.0,
        },
        SubscriptionTier.PREMIUM: {
            "max_bots": 20,
            "max_exchanges": 10,
            "log_retention_days": 90,
            "backup_retention_days": 90,
            "enable_webhooks": True,
            "enable_advanced_strategies": True,
            "price_monthly": 299.0,
        },
    }

    config = tier_config.get(upgrade_data.new_tier)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier"
        )

    # 更新订阅
    subscription.tier = upgrade_data.new_tier
    subscription.status = SubscriptionStatus.ACTIVE
    for key, value in config.items():
        setattr(subscription, key, value)

    db.commit()

    return {"message": "Subscription upgraded successfully"}


# ==================== 租户管理（客户栈）====================

@app.get("/tenants/me", response_model=TenantResponse)
def get_my_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """获取当前用户的租户（客户栈）信息"""
    tenant = db.query(Tenant).filter(
        Tenant.user_id == current_user.id,
        Tenant.status != TenantStatus.TERMINATED
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active tenant found. Please provision one first."
        )

    return TenantResponse.from_orm(tenant)


@app.post("/tenants/provision", response_model=TenantResponse)
def provision_tenant(
    current_user: User = Depends(get_current_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db_session)
):
    """
    创建客户栈（Provision）

    这是最关键的接口！会触发：
    1. 生成租户 ID 和子域名
    2. 调用编排器创建 Docker 栈
    3. 初始化数据库
    4. 配置 Traefik 路由
    """
    # 检查是否已有租户
    existing_tenant = db.query(Tenant).filter(
        Tenant.user_id == current_user.id,
        Tenant.status != TenantStatus.TERMINATED
    ).first()

    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant already exists"
        )

    # 创建租户记录
    tenant_code = f"u{current_user.id[:8]}"
    subdomain = f"{tenant_code}.yourdomain.com"  # 替换为实际域名

    new_tenant = Tenant(
        user_id=current_user.id,
        subscription_id=subscription.id,
        tenant_code=tenant_code,
        subdomain=subdomain,
        api_subdomain=f"api-{tenant_code}.yourdomain.com",
        dashboard_url=f"https://{subdomain}",
        api_url=f"https://api-{tenant_code}.yourdomain.com",
        status=TenantStatus.PROVISIONING,
    )

    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)

    # 调用编排器（异步任务）
    # from core.orchestrator import provision_tenant_stack
    # provision_tenant_stack.delay(new_tenant.id)

    return TenantResponse.from_orm(new_tenant)


# ==================== Bot 管理 ====================

@app.get("/bots", response_model=List[BotResponse])
def list_bots(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """获取当前用户的所有 Bot"""
    bots = db.query(Bot).filter(Bot.user_id == current_user.id).all()
    return [BotResponse.from_orm(bot) for bot in bots]


@app.post("/bots", response_model=BotResponse)
def create_bot(
    bot_data: BotCreate,
    current_user: User = Depends(get_current_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db_session)
):
    """
    创建 Bot

    需要检查配额限制
    """
    # 检查配额
    current_bot_count = db.query(Bot).filter(
        Bot.user_id == current_user.id,
        Bot.status != BotStatus.STOPPED
    ).count()

    if current_bot_count >= subscription.max_bots:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bot limit reached ({subscription.max_bots}). Please upgrade your plan."
        )

    # 获取租户
    tenant = db.query(Tenant).filter(
        Tenant.user_id == current_user.id,
        Tenant.status == TenantStatus.RUNNING
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No running tenant found"
        )

    # 创建 Bot
    new_bot = Bot(
        user_id=current_user.id,
        tenant_id=tenant.id,
        exchange_connection_id=bot_data.exchange_connection_id,
        bot_name=bot_data.bot_name,
        description=bot_data.description,
        strategy_template=bot_data.strategy_template,
        strategy_config=bot_data.strategy_config,
        trading_pair=bot_data.trading_pair,
        market_type=bot_data.market_type,
        risk_config=bot_data.risk_config,
    )

    db.add(new_bot)
    db.commit()
    db.refresh(new_bot)

    return BotResponse.from_orm(new_bot)


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

    # 调用编排器启动 Bot
    # from core.orchestrator import start_bot_container
    # start_bot_container.delay(bot.id)

    bot.status = BotStatus.STARTING
    bot.started_at = datetime.utcnow()
    db.commit()

    return {"message": "Bot is starting..."}


@app.post("/bots/{bot_id}/stop")
def stop_bot(
    bot_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """停止 Bot"""
    bot = db.query(Bot).filter(
        Bot.id == bot_id,
        Bot.user_id == current_user.id
    ).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found"
        )

    # 调用编排器停止 Bot
    # from core.orchestrator import stop_bot_container
    # stop_bot_container.delay(bot.id)

    bot.status = BotStatus.STOPPING
    bot.stopped_at = datetime.utcnow()
    db.commit()

    return {"message": "Bot is stopping..."}


# ==================== 告警管理 ====================

@app.get("/alerts", response_model=List[AlertResponse])
def list_alerts(
    severity: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """获取告警列表"""
    query = db.query(Alert).filter(Alert.user_id == current_user.id)

    if severity:
        query = query.filter(Alert.severity == severity)

    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return [AlertResponse.from_orm(alert) for alert in alerts]


# ==================== 工单系统 ====================

@app.post("/tickets", response_model=TicketResponse)
def create_ticket(
    ticket_data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """创建工单"""
    from database.models import Ticket
    import random

    # 生成工单号
    ticket_number = f"TK-{datetime.utcnow().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    new_ticket = Ticket(
        user_id=current_user.id,
        ticket_number=ticket_number,
        subject=ticket_data.subject,
        description=ticket_data.description,
        category=ticket_data.category,
        priority=ticket_data.priority,
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    return TicketResponse.from_orm(new_ticket)


@app.get("/tickets", response_model=List[TicketResponse])
def list_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """获取工单列表"""
    from database.models import Ticket

    tickets = db.query(Ticket).filter(
        Ticket.user_id == current_user.id
    ).order_by(Ticket.created_at.desc()).all()

    return [TicketResponse.from_orm(ticket) for ticket in tickets]


# ==================== 启动应用 ====================

if __name__ == "__main__":
    # 初始化数据库
    init_database()

    # 启动 API 服务
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式
    )
