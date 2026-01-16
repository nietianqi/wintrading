"""
API Dependencies
用于认证、权限检查、依赖注入
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime
import os

from database import get_db_session
from database.models import User, Subscription, SubscriptionStatus

security = HTTPBearer()

# JWT 配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session)
) -> User:
    """
    从 JWT Token 获取当前用户

    依赖注入示例：
    @app.get("/protected")
    def protected_route(current_user: User = Depends(get_current_user)):
        return {"user_id": current_user.id}
    """
    token = credentials.credentials

    try:
        # 解码 JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    # 查询用户
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def require_active_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
) -> Subscription:
    """
    要求用户有有效订阅

    依赖注入示例：
    @app.post("/bots")
    def create_bot(
        subscription: Subscription = Depends(require_active_subscription)
    ):
        if subscription.max_bots <= current_bots:
            raise HTTPException(...)
    """
    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
    ).first()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No active subscription. Please subscribe to continue.",
        )

    # 检查试用期是否过期
    if subscription.status == SubscriptionStatus.TRIAL:
        if subscription.trial_ends_at and subscription.trial_ends_at < datetime.utcnow():
            # 过期，更新状态
            subscription.status = SubscriptionStatus.SUSPENDED
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Trial period expired. Please upgrade to continue.",
            )

    # 检查付费订阅是否到期
    if subscription.status == SubscriptionStatus.ACTIVE:
        if subscription.billing_cycle_end and subscription.billing_cycle_end < datetime.utcnow():
            # 进入宽限期
            subscription.status = SubscriptionStatus.GRACE_PERIOD
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription expired. Please renew to continue.",
            )

    return subscription


def require_verified_email(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    要求用户邮箱已验证

    依赖注入示例：
    @app.post("/sensitive-action")
    def sensitive_action(
        current_user: User = Depends(require_verified_email)
    ):
        ...
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email first.",
        )

    return current_user


def check_bot_quota(
    current_user: User = Depends(get_current_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db_session)
) -> bool:
    """
    检查 Bot 配额

    返回是否还可以创建 Bot
    """
    from database.models import Bot, BotStatus

    current_bot_count = db.query(Bot).filter(
        Bot.user_id == current_user.id,
        Bot.status != BotStatus.STOPPED
    ).count()

    if current_bot_count >= subscription.max_bots:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bot limit reached ({subscription.max_bots}). Please upgrade your plan.",
        )

    return True


def check_exchange_quota(
    current_user: User = Depends(get_current_user),
    subscription: Subscription = Depends(require_active_subscription),
    db: Session = Depends(get_db_session)
) -> bool:
    """
    检查交易所连接配额

    返回是否还可以添加交易所连接
    """
    from database.models import ExchangeConnection

    current_exchange_count = db.query(ExchangeConnection).filter(
        ExchangeConnection.user_id == current_user.id,
        ExchangeConnection.is_active == True
    ).count()

    if current_exchange_count >= subscription.max_exchanges:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Exchange connection limit reached ({subscription.max_exchanges}). "
                   f"Please upgrade your plan.",
        )

    return True


def require_webhook_access(
    subscription: Subscription = Depends(require_active_subscription)
) -> Subscription:
    """
    要求订阅支持 Webhook 功能

    依赖注入示例：
    @app.post("/webhooks")
    def create_webhook(
        subscription: Subscription = Depends(require_webhook_access)
    ):
        ...
    """
    if not subscription.enable_webhooks:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook feature not available in your plan. Please upgrade.",
        )

    return subscription


def require_advanced_strategies(
    subscription: Subscription = Depends(require_active_subscription)
) -> Subscription:
    """
    要求订阅支持高级策略

    依赖注入示例：
    @app.post("/bots/custom-strategy")
    def create_custom_strategy_bot(
        subscription: Subscription = Depends(require_advanced_strategies)
    ):
        ...
    """
    if not subscription.enable_advanced_strategies:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Advanced strategies not available in your plan. Please upgrade.",
        )

    return subscription


# ==================== 运维管理员权限（后台接口） ====================

def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    要求管理员权限

    实际项目应该在 User 表添加 role 字段
    """
    # 简化版：检查是否是特定用户
    ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "admin@yourdomain.com").split(",")

    if current_user.email not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user


def require_support_staff(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    要求客服权限

    可以查看用户信息和工单，但不能操作资源
    """
    SUPPORT_EMAILS = os.getenv("SUPPORT_EMAILS", "support@yourdomain.com").split(",")
    ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "admin@yourdomain.com").split(",")

    if current_user.email not in SUPPORT_EMAILS + ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Support staff access required",
        )

    return current_user


# ==================== 速率限制（可选） ====================

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

# 简单的内存速率限制（生产环境应使用 Redis）
_rate_limit_store: Dict[str, list] = defaultdict(list)


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60
):
    """
    速率限制装饰器

    使用示例：
    @app.post("/expensive-operation")
    @rate_limit(max_requests=10, window_seconds=60)
    def expensive_operation(
        current_user: User = Depends(get_current_user)
    ):
        ...
    """
    def decorator(
        current_user: User = Depends(get_current_user)
    ) -> User:
        now = datetime.utcnow()
        user_requests = _rate_limit_store[current_user.id]

        # 清理过期请求
        cutoff = now - timedelta(seconds=window_seconds)
        user_requests[:] = [req_time for req_time in user_requests if req_time > cutoff]

        # 检查速率
        if len(user_requests) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds} seconds.",
            )

        # 记录请求
        user_requests.append(now)

        return current_user

    return decorator
