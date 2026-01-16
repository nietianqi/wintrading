#!/usr/bin/env python3
"""
系统初始化脚本
用于首次部署时初始化数据库和配置
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_database, get_db
from database.models import (
    User, Subscription, SubscriptionTier, SubscriptionStatus, SystemConfig
)
from passlib.context import CryptContext
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_admin_user():
    """创建管理员用户"""
    print("📝 Creating admin user...")

    admin_email = os.getenv("ADMIN_EMAIL", "admin@yourdomain.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")

    with get_db() as db:
        # 检查管理员是否已存在
        existing_admin = db.query(User).filter(User.email == admin_email).first()
        if existing_admin:
            print(f"⚠️  Admin user already exists: {admin_email}")
            return

        # 创建管理员用户
        admin = User(
            email=admin_email,
            username="admin",
            password_hash=pwd_context.hash(admin_password),
            full_name="System Administrator",
            is_active=True,
            is_verified=True,
            email_verified_at=datetime.utcnow(),
        )

        db.add(admin)
        db.flush()

        # 创建管理员订阅（Premium）
        admin_subscription = Subscription(
            user_id=admin.id,
            tier=SubscriptionTier.PREMIUM,
            status=SubscriptionStatus.ACTIVE,
            max_bots=100,
            max_exchanges=20,
            log_retention_days=365,
            backup_retention_days=365,
            enable_webhooks=True,
            enable_advanced_strategies=True,
            enable_api_access=True,
        )

        db.add(admin_subscription)
        db.commit()

        print(f"✓ Admin user created: {admin_email}")
        print(f"  Default password: {admin_password}")
        print(f"  ⚠️  Please change the password after first login!")


def create_system_configs():
    """创建系统配置"""
    print("⚙️  Creating system configurations...")

    configs = [
        {
            "config_key": "hummingbot_version",
            "config_value": "latest",
            "config_type": "string",
            "description": "Default Hummingbot version for new tenants",
        },
        {
            "config_key": "dashboard_version",
            "config_value": "latest",
            "config_type": "string",
            "description": "Default Dashboard version for new tenants",
        },
        {
            "config_key": "auto_backup_enabled",
            "config_value": "true",
            "config_type": "bool",
            "description": "Enable automatic daily backups",
        },
        {
            "config_key": "maintenance_mode",
            "config_value": "false",
            "config_type": "bool",
            "description": "Maintenance mode (disable new registrations)",
        },
        {
            "config_key": "trial_period_days",
            "config_value": "14",
            "config_type": "int",
            "description": "Default trial period in days",
        },
    ]

    with get_db() as db:
        for config_data in configs:
            existing = db.query(SystemConfig).filter(
                SystemConfig.config_key == config_data["config_key"]
            ).first()

            if not existing:
                config = SystemConfig(**config_data)
                db.add(config)

        db.commit()

    print(f"✓ System configurations created")


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 Hummingbot SaaS Platform - System Initialization")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n1️⃣  Initializing database...")
    init_database()
    print("✓ Database initialized")

    # 2. 创建管理员用户
    print("\n2️⃣  Creating admin user...")
    create_admin_user()

    # 3. 创建系统配置
    print("\n3️⃣  Creating system configurations...")
    create_system_configs()

    print("\n" + "=" * 60)
    print("✅ System initialization completed!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start the Portal API: python api/main.py")
    print("2. Access the API docs: http://localhost:8000/docs")
    print("3. Login with admin credentials and change password")
    print("\n")


if __name__ == "__main__":
    main()
