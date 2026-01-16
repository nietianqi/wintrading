"""
备份和恢复管理
自动备份租户数据（数据库、配置、日志）
"""
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
import tarfile

from database import get_db
from database.models import Backup, Tenant, Subscription


class BackupManager:
    """
    备份管理器

    功能：
    1. 创建备份（全量/增量）
    2. 恢复备份
    3. 自动清理过期备份
    4. 备份验证
    """

    def __init__(self, backup_base_path: str = "/srv/backups"):
        """
        初始化备份管理器

        Args:
            backup_base_path: 备份存储基础路径
        """
        self.backup_base_path = Path(backup_base_path)
        self.backup_base_path.mkdir(parents=True, exist_ok=True)

    def create_backup(
        self,
        tenant_id: str,
        backup_type: str = "full",
        include_logs: bool = False,
    ) -> Backup:
        """
        创建备份

        Args:
            tenant_id: 租户 ID
            backup_type: 备份类型（full/config_only/pre_upgrade）
            include_logs: 是否包含日志（日志可能很大）

        Returns:
            Backup 对象
        """
        print(f"🗄️  Creating {backup_type} backup for tenant {tenant_id}")

        with get_db() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            subscription = db.query(Subscription).filter(
                Subscription.id == tenant.subscription_id
            ).first()

            # 创建备份记录
            backup = Backup(
                tenant_id=tenant_id,
                backup_type=backup_type,
                includes_database=backup_type in ["full", "pre_upgrade"],
                includes_configs=True,
                includes_logs=include_logs,
                status="running",
            )

            db.add(backup)
            db.commit()
            db.refresh(backup)

            try:
                # 执行备份
                backup_path = self._perform_backup(tenant, backup, include_logs)

                # 计算文件大小
                file_size = sum(
                    f.stat().st_size for f in backup_path.rglob('*') if f.is_file()
                )

                # 计算过期时间（根据套餐）
                expires_at = datetime.utcnow() + timedelta(
                    days=subscription.backup_retention_days
                )

                # 更新备份记录
                backup.backup_path = str(backup_path)
                backup.file_size_bytes = file_size
                backup.status = "completed"
                backup.completed_at = datetime.utcnow()
                backup.expires_at = expires_at

                db.commit()

                print(f"✓ Backup completed: {backup_path}")
                return backup

            except Exception as e:
                print(f"✗ Backup failed: {e}")
                backup.status = "failed"
                backup.error_message = str(e)
                db.commit()
                raise

    def _perform_backup(
        self,
        tenant: Tenant,
        backup: Backup,
        include_logs: bool
    ) -> Path:
        """
        执行实际备份操作

        备份内容：
        1. PostgreSQL 数据库导出（pg_dump）
        2. 配置文件
        3. Hummingbot 数据目录
        4. 日志（可选）
        """
        tenant_path = Path(tenant.deployment_path)

        # 创建备份目录
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.backup_base_path / tenant.tenant_code / f"{backup.backup_type}_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # 1. 备份数据库
        if backup.includes_database:
            self._backup_database(tenant, backup_dir)

        # 2. 备份配置文件
        if backup.includes_configs:
            self._backup_configs(tenant_path, backup_dir)

        # 3. 备份 Hummingbot 数据
        self._backup_hummingbot_data(tenant_path, backup_dir)

        # 4. 备份日志（可选）
        if include_logs:
            self._backup_logs(tenant_path, backup_dir)

        # 5. 压缩备份
        archive_path = backup_dir.parent / f"{backup_dir.name}.tar.gz"
        self._compress_backup(backup_dir, archive_path)

        # 删除未压缩的备份目录
        shutil.rmtree(backup_dir)

        return archive_path

    def _backup_database(self, tenant: Tenant, backup_dir: Path):
        """
        备份 PostgreSQL 数据库

        使用 pg_dump
        """
        print(f"  📦 Backing up database...")

        db_backup_file = backup_dir / "database.sql"

        # 获取数据库容器名
        container_name = f"{tenant.tenant_code}-postgres"

        # 执行 pg_dump
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "pg_dump", "-U", "hummingbot", "-d", "hummingbot"
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Database backup failed: {result.stderr}")

        # 保存备份
        db_backup_file.write_text(result.stdout)
        print(f"  ✓ Database backed up ({db_backup_file.stat().st_size / 1024 / 1024:.2f} MB)")

    def _backup_configs(self, tenant_path: Path, backup_dir: Path):
        """备份配置文件"""
        print(f"  📦 Backing up configs...")

        config_src = tenant_path / "configs"
        config_dst = backup_dir / "configs"

        if config_src.exists():
            shutil.copytree(config_src, config_dst)
            print(f"  ✓ Configs backed up")

    def _backup_hummingbot_data(self, tenant_path: Path, backup_dir: Path):
        """备份 Hummingbot 数据目录"""
        print(f"  📦 Backing up Hummingbot data...")

        data_src = tenant_path / "data" / "hummingbot"
        data_dst = backup_dir / "hummingbot_data"

        if data_src.exists():
            shutil.copytree(data_src, data_dst)
            print(f"  ✓ Hummingbot data backed up")

    def _backup_logs(self, tenant_path: Path, backup_dir: Path):
        """备份日志"""
        print(f"  📦 Backing up logs...")

        logs_src = tenant_path / "logs"
        logs_dst = backup_dir / "logs"

        if logs_src.exists():
            shutil.copytree(logs_src, logs_dst)
            print(f"  ✓ Logs backed up")

    def _compress_backup(self, backup_dir: Path, archive_path: Path):
        """压缩备份目录"""
        print(f"  🗜️  Compressing backup...")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(backup_dir, arcname=backup_dir.name)

        print(f"  ✓ Backup compressed: {archive_path} ({archive_path.stat().st_size / 1024 / 1024:.2f} MB)")

    def restore_backup(self, backup_id: str, tenant_id: str) -> bool:
        """
        恢复备份

        流程：
        1. 停止租户栈
        2. 解压备份
        3. 恢复数据库
        4. 恢复配置文件
        5. 恢复数据目录
        6. 启动租户栈
        7. 健康检查

        Args:
            backup_id: 备份 ID
            tenant_id: 租户 ID

        Returns:
            是否成功
        """
        print(f"🔄 Restoring backup {backup_id} for tenant {tenant_id}")

        with get_db() as db:
            backup = db.query(Backup).filter(Backup.id == backup_id).first()
            if not backup:
                raise ValueError(f"Backup {backup_id} not found")

            if backup.status != "completed":
                raise ValueError(f"Backup is not in completed state")

            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            try:
                # 1. 停止租户栈
                from core.orchestrator import TenantOrchestrator
                orchestrator = TenantOrchestrator()
                orchestrator.stop_tenant_stack(tenant_id)

                # 2. 解压备份
                backup_path = Path(backup.backup_path)
                restore_dir = backup_path.parent / "restore_temp"
                restore_dir.mkdir(exist_ok=True)

                with tarfile.open(backup_path, "r:gz") as tar:
                    tar.extractall(restore_dir)

                extracted_dir = restore_dir / backup_path.stem.replace(".tar", "")

                # 3. 恢复数据库
                if backup.includes_database:
                    self._restore_database(tenant, extracted_dir)

                # 4. 恢复配置
                if backup.includes_configs:
                    self._restore_configs(tenant, extracted_dir)

                # 5. 恢复数据
                self._restore_hummingbot_data(tenant, extracted_dir)

                # 6. 启动租户栈
                orchestrator._start_stack(Path(tenant.deployment_path))

                # 7. 健康检查
                orchestrator._wait_for_healthy(Path(tenant.deployment_path))

                # 清理临时文件
                shutil.rmtree(restore_dir)

                print(f"✓ Backup restored successfully")
                return True

            except Exception as e:
                print(f"✗ Restore failed: {e}")
                raise

    def _restore_database(self, tenant: Tenant, restore_dir: Path):
        """恢复数据库"""
        print(f"  📥 Restoring database...")

        db_backup_file = restore_dir / "database.sql"
        if not db_backup_file.exists():
            print(f"  ⚠️  No database backup found, skipping")
            return

        container_name = f"{tenant.tenant_code}-postgres"

        # 先删除现有数据库
        subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "hummingbot", "-c", "DROP DATABASE IF EXISTS hummingbot;"
            ],
            check=True,
        )

        subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "hummingbot", "-c", "CREATE DATABASE hummingbot;"
            ],
            check=True,
        )

        # 恢复数据
        with db_backup_file.open() as f:
            subprocess.run(
                [
                    "docker", "exec", "-i", container_name,
                    "psql", "-U", "hummingbot", "-d", "hummingbot"
                ],
                stdin=f,
                check=True,
            )

        print(f"  ✓ Database restored")

    def _restore_configs(self, tenant: Tenant, restore_dir: Path):
        """恢复配置"""
        print(f"  📥 Restoring configs...")

        config_src = restore_dir / "configs"
        config_dst = Path(tenant.deployment_path) / "configs"

        if config_src.exists():
            if config_dst.exists():
                shutil.rmtree(config_dst)
            shutil.copytree(config_src, config_dst)
            print(f"  ✓ Configs restored")

    def _restore_hummingbot_data(self, tenant: Tenant, restore_dir: Path):
        """恢复 Hummingbot 数据"""
        print(f"  📥 Restoring Hummingbot data...")

        data_src = restore_dir / "hummingbot_data"
        data_dst = Path(tenant.deployment_path) / "data" / "hummingbot"

        if data_src.exists():
            if data_dst.exists():
                shutil.rmtree(data_dst)
            shutil.copytree(data_src, data_dst)
            print(f"  ✓ Hummingbot data restored")

    def cleanup_expired_backups(self):
        """
        清理过期备份

        应该作为定时任务运行（每天）
        """
        print(f"🗑️  Cleaning up expired backups...")

        with get_db() as db:
            expired_backups = db.query(Backup).filter(
                Backup.expires_at < datetime.utcnow(),
                Backup.status == "completed"
            ).all()

            count = 0
            for backup in expired_backups:
                try:
                    # 删除备份文件
                    backup_path = Path(backup.backup_path)
                    if backup_path.exists():
                        backup_path.unlink()

                    # 删除数据库记录
                    db.delete(backup)
                    count += 1

                except Exception as e:
                    print(f"  ⚠️  Failed to delete backup {backup.id}: {e}")

            db.commit()
            print(f"✓ Cleaned up {count} expired backups")

    def list_backups(self, tenant_id: str) -> List[Backup]:
        """获取租户的所有备份"""
        with get_db() as db:
            backups = db.query(Backup).filter(
                Backup.tenant_id == tenant_id
            ).order_by(Backup.created_at.desc()).all()

            return backups


# ==================== 自动备份调度器 ====================

class BackupScheduler:
    """
    备份调度器

    定时任务：
    1. 每天凌晨 2 点自动备份所有租户
    2. 每天清理过期备份
    """

    def __init__(self):
        self.backup_manager = BackupManager()

    def run_daily_backup(self):
        """运行每日备份（所有活跃租户）"""
        print(f"🕐 Running daily backup at {datetime.utcnow()}")

        with get_db() as db:
            from database.models import TenantStatus

            active_tenants = db.query(Tenant).filter(
                Tenant.status == TenantStatus.RUNNING
            ).all()

            success_count = 0
            fail_count = 0

            for tenant in active_tenants:
                try:
                    self.backup_manager.create_backup(
                        tenant.id,
                        backup_type="full",
                        include_logs=False,  # 日志太大，不包含
                    )
                    success_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to backup tenant {tenant.tenant_code}: {e}")
                    fail_count += 1

            print(f"✓ Daily backup completed: {success_count} success, {fail_count} failed")

    def run_cleanup(self):
        """运行清理任务"""
        self.backup_manager.cleanup_expired_backups()


# ==================== 使用示例 ====================

if __name__ == "__main__":
    manager = BackupManager()

    # 创建备份
    # backup = manager.create_backup("tenant-id", backup_type="full")

    # 恢复备份
    # manager.restore_backup("backup-id", "tenant-id")

    # 清理过期备份
    # manager.cleanup_expired_backups()
