#!/usr/bin/env python3
"""
清理过期备份脚本
Cron: 0 3 * * * (每天凌晨 3 点)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backup import BackupScheduler
from datetime import datetime


def main():
    print(f"🗑️  Cleanup Started at {datetime.utcnow()}")
    print("=" * 60)

    try:
        scheduler = BackupScheduler()
        scheduler.run_cleanup()
        print("\n✓ Cleanup completed successfully")

    except Exception as e:
        print(f"\n✗ Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
