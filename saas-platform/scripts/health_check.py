#!/usr/bin/env python3
"""
租户健康检查脚本
Cron: */5 * * * * (每 5 分钟)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db
from database.models import Tenant, TenantStatus
from core.orchestrator import TenantOrchestrator
from core.notifications import NotificationManager, AlertTemplates
from datetime import datetime


def main():
    print(f"🔍 Health Check Started at {datetime.utcnow()}")
    print("=" * 60)

    orchestrator = TenantOrchestrator()
    notifier = NotificationManager()

    with get_db() as db:
        # 获取所有运行中的租户
        active_tenants = db.query(Tenant).filter(
            Tenant.status == TenantStatus.RUNNING
        ).all()

        print(f"Checking {len(active_tenants)} active tenants...")

        unhealthy_count = 0
        for tenant in active_tenants:
            try:
                # 检查健康状态
                health = orchestrator.check_tenant_health(tenant.id)

                # 如果不健康，发送告警
                if health["health"] == "unhealthy":
                    alert_data = AlertTemplates.tenant_unhealthy(
                        tenant.tenant_code,
                        "Container not running or not responding"
                    )

                    notifier.create_alert(
                        user_id=tenant.user_id,
                        tenant_id=tenant.id,
                        **alert_data
                    )

                    unhealthy_count += 1
                    print(f"  ⚠️  {tenant.tenant_code}: UNHEALTHY")
                else:
                    print(f"  ✓ {tenant.tenant_code}: healthy")

            except Exception as e:
                print(f"  ✗ {tenant.tenant_code}: error - {e}")
                unhealthy_count += 1

    print("\n" + "=" * 60)
    if unhealthy_count == 0:
        print("✓ All tenants are healthy")
    else:
        print(f"⚠️  {unhealthy_count} tenants are unhealthy")


if __name__ == "__main__":
    main()
