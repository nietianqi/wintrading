#!/usr/bin/env python3
"""
每日备份脚本
Cron: 0 2 * * * (每天凌晨 2 点)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backup import BackupScheduler
from datetime import datetime

def main():
    print(f"⏰ Daily Backup Started at {datetime.utcnow()}")
    print("=" * 60)

    try:
        scheduler = BackupScheduler()
        scheduler.run_daily_backup()
        print("\n✓ Daily backup completed successfully")

    except Exception as e:
        print(f"\n✗ Daily backup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
