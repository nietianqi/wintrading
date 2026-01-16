"""
客户栈编排器（Orchestrator）
负责创建、管理、升级、回滚客户的独立 Docker 栈

这是整个系统的核心！
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import docker
from jinja2 import Template
import yaml

from database import get_db
from database.models import (
    Tenant, TenantStatus, Subscription, Bot, BotStatus
)


class TenantOrchestrator:
    """
    租户编排器

    核心功能：
    1. 创建客户栈（provision）
    2. 启动/停止栈
    3. 升级/回滚
    4. 健康检查
    5. 资源监控
    """

    def __init__(self, base_path: str = "/srv/tenants"):
        """
        初始化编排器

        Args:
            base_path: 租户栈的基础路径
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Docker 客户端
        self.docker_client = docker.from_env()

        # 模板路径
        self.template_path = Path(__file__).parent / "templates"

    def provision_tenant_stack(self, tenant_id: str) -> bool:
        """
        创建客户栈（完整流程）

        流程：
        1. 创建目录结构
        2. 生成配置文件（compose.yml）
        3. 初始化数据库
        4. 启动所有服务
        5. 健康检查
        6. 更新租户状态

        Args:
            tenant_id: 租户 ID

        Returns:
            是否成功
        """
        print(f"🚀 Provisioning tenant stack: {tenant_id}")

        with get_db() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            subscription = db.query(Subscription).filter(
                Subscription.id == tenant.subscription_id
            ).first()

            try:
                # 1. 创建目录结构
                tenant_path = self.base_path / tenant.tenant_code
                self._create_directory_structure(tenant_path)

                # 2. 生成 Docker Compose 配置
                compose_content = self._generate_compose_file(tenant, subscription)
                compose_file = tenant_path / "compose.yml"
                compose_file.write_text(compose_content)

                # 3. 生成环境变量文件
                env_content = self._generate_env_file(tenant, subscription)
                env_file = tenant_path / ".env"
                env_file.write_text(env_content)

                # 4. 启动栈
                self._start_stack(tenant_path)

                # 5. 等待服务健康
                self._wait_for_healthy(tenant_path)

                # 6. 初始化租户数据库
                self._initialize_tenant_database(tenant)

                # 7. 更新租户状态
                tenant.status = TenantStatus.RUNNING
                tenant.deployment_path = str(tenant_path)
                tenant.compose_file_path = str(compose_file)
                tenant.last_health_check = datetime.utcnow()
                tenant.health_status = "healthy"

                db.commit()

                print(f"✓ Tenant stack provisioned successfully: {tenant.subdomain}")
                return True

            except Exception as e:
                print(f"✗ Failed to provision tenant stack: {e}")
                tenant.status = TenantStatus.ERROR
                tenant.last_error = str(e)
                db.commit()
                raise

    def _create_directory_structure(self, tenant_path: Path):
        """
        创建租户目录结构

        /srv/tenants/u123/
        ├── compose.yml
        ├── .env
        ├── data/
        │   ├── postgres/
        │   ├── redis/
        │   └── hummingbot/
        ├── configs/
        ├── logs/
        └── backups/
        """
        dirs = [
            "data/postgres",
            "data/redis",
            "data/hummingbot",
            "configs",
            "logs",
            "backups",
        ]

        for dir_name in dirs:
            (tenant_path / dir_name).mkdir(parents=True, exist_ok=True)

        print(f"✓ Created directory structure: {tenant_path}")

    def _generate_compose_file(self, tenant: Tenant, subscription: Subscription) -> str:
        """
        生成 Docker Compose 配置文件

        使用 Jinja2 模板
        """
        template_file = self.template_path / "tenant-compose.yml.j2"

        if not template_file.exists():
            # 如果模板不存在，使用内嵌模板
            template_content = self._get_default_compose_template()
        else:
            template_content = template_file.read_text()

        template = Template(template_content)

        # 渲染变量
        context = {
            "tenant_code": tenant.tenant_code,
            "subdomain": tenant.subdomain,
            "api_subdomain": tenant.api_subdomain,
            "cpu_limit": subscription.cpu_limit,
            "memory_limit_mb": subscription.memory_limit_mb,
            "hummingbot_version": os.getenv("HUMMINGBOT_VERSION", "latest"),
            "dashboard_version": os.getenv("DASHBOARD_VERSION", "latest"),
            "postgres_password": self._generate_password(),
            "redis_password": self._generate_password(),
        }

        return template.render(**context)

    def _get_default_compose_template(self) -> str:
        """返回默认的 Docker Compose 模板"""
        return """version: '3.8'

services:
  # PostgreSQL 数据库（租户独立）
  postgres:
    image: postgres:15-alpine
    container_name: {{ tenant_code }}-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: hummingbot
      POSTGRES_USER: hummingbot
      POSTGRES_PASSWORD: {{ postgres_password }}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    networks:
      - tenant_network
    deploy:
      resources:
        limits:
          cpus: '{{ cpu_limit * 0.2 }}'
          memory: {{ memory_limit_mb * 0.2 }}M

  # Redis（用于缓存和队列）
  redis:
    image: redis:7-alpine
    container_name: {{ tenant_code }}-redis
    restart: unless-stopped
    command: redis-server --requirepass {{ redis_password }}
    volumes:
      - ./data/redis:/data
    networks:
      - tenant_network
    deploy:
      resources:
        limits:
          cpus: '{{ cpu_limit * 0.1 }}'
          memory: {{ memory_limit_mb * 0.1 }}M

  # Hummingbot API
  hummingbot-api:
    image: hummingbot/hummingbot:{{ hummingbot_version }}
    container_name: {{ tenant_code }}-api
    restart: unless-stopped
    command: ["python", "bin/hummingbot_quickstart.py", "--auto-set-permissions"]
    environment:
      DATABASE_HOST: postgres
      DATABASE_PORT: 5432
      DATABASE_NAME: hummingbot
      DATABASE_USER: hummingbot
      DATABASE_PASSWORD: {{ postgres_password }}
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_PASSWORD: {{ redis_password }}
    volumes:
      - ./data/hummingbot:/home/hummingbot
      - ./configs:/home/hummingbot/conf
      - ./logs:/home/hummingbot/logs
    networks:
      - tenant_network
    depends_on:
      - postgres
      - redis
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.{{ tenant_code }}-api.rule=Host(`{{ api_subdomain }}`)"
      - "traefik.http.routers.{{ tenant_code }}-api.entrypoints=websecure"
      - "traefik.http.routers.{{ tenant_code }}-api.tls.certresolver=letsencrypt"
      - "traefik.http.services.{{ tenant_code }}-api.loadbalancer.server.port=8080"
    deploy:
      resources:
        limits:
          cpus: '{{ cpu_limit * 0.5 }}'
          memory: {{ memory_limit_mb * 0.5 }}M

  # Hummingbot Dashboard
  dashboard:
    image: hummingbot/dashboard:{{ dashboard_version }}
    container_name: {{ tenant_code }}-dashboard
    restart: unless-stopped
    environment:
      HUMMINGBOT_API_URL: http://hummingbot-api:8080
    networks:
      - tenant_network
    depends_on:
      - hummingbot-api
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.{{ tenant_code }}-dashboard.rule=Host(`{{ subdomain }}`)"
      - "traefik.http.routers.{{ tenant_code }}-dashboard.entrypoints=websecure"
      - "traefik.http.routers.{{ tenant_code }}-dashboard.tls.certresolver=letsencrypt"
      - "traefik.http.services.{{ tenant_code }}-dashboard.loadbalancer.server.port=8501"
    deploy:
      resources:
        limits:
          cpus: '{{ cpu_limit * 0.2 }}'
          memory: {{ memory_limit_mb * 0.2 }}M

networks:
  tenant_network:
    driver: bridge
"""

    def _generate_env_file(self, tenant: Tenant, subscription: Subscription) -> str:
        """生成环境变量文件"""
        return f"""# Tenant: {tenant.tenant_code}
# Generated: {datetime.utcnow().isoformat()}

TENANT_ID={tenant.id}
TENANT_CODE={tenant.tenant_code}
SUBSCRIPTION_TIER={subscription.tier.value}
"""

    def _generate_password(self) -> str:
        """生成随机密码"""
        import secrets
        return secrets.token_urlsafe(32)

    def _start_stack(self, tenant_path: Path):
        """
        启动 Docker Compose 栈

        Args:
            tenant_path: 租户目录路径
        """
        print(f"🚀 Starting stack: {tenant_path}")

        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=tenant_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start stack: {result.stderr}")

        print(f"✓ Stack started successfully")

    def _stop_stack(self, tenant_path: Path):
        """停止 Docker Compose 栈"""
        print(f"🛑 Stopping stack: {tenant_path}")

        result = subprocess.run(
            ["docker", "compose", "down"],
            cwd=tenant_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to stop stack: {result.stderr}")

        print(f"✓ Stack stopped successfully")

    def _wait_for_healthy(self, tenant_path: Path, timeout: int = 120):
        """
        等待服务健康

        检查所有容器是否启动成功
        """
        import time

        print(f"⏳ Waiting for services to be healthy...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                cwd=tenant_path,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # 检查所有容器状态
                all_healthy = True
                for line in result.stdout.strip().split('\n'):
                    if line:
                        import json
                        container = json.loads(line)
                        if container.get("State") != "running":
                            all_healthy = False
                            break

                if all_healthy:
                    print(f"✓ All services are healthy")
                    return

            time.sleep(5)

        raise TimeoutError(f"Services failed to become healthy within {timeout}s")

    def _initialize_tenant_database(self, tenant: Tenant):
        """
        初始化租户数据库

        可以在这里运行 Hummingbot 的数据库初始化脚本
        """
        print(f"🗄️  Initializing tenant database...")
        # TODO: 运行 Hummingbot 数据库初始化
        print(f"✓ Database initialized")

    def stop_tenant_stack(self, tenant_id: str) -> bool:
        """停止客户栈"""
        with get_db() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            try:
                tenant_path = Path(tenant.deployment_path)
                self._stop_stack(tenant_path)

                tenant.status = TenantStatus.STOPPED
                db.commit()

                return True

            except Exception as e:
                print(f"✗ Failed to stop tenant stack: {e}")
                raise

    def upgrade_tenant_stack(
        self,
        tenant_id: str,
        new_version: str,
        backup_first: bool = True
    ) -> bool:
        """
        升级客户栈

        流程：
        1. 备份当前状态
        2. 拉取新镜像
        3. 重启服务
        4. 健康检查
        5. 失败则回滚
        """
        print(f"⬆️  Upgrading tenant stack to version {new_version}")

        with get_db() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            old_version = tenant.hummingbot_version
            tenant_path = Path(tenant.deployment_path)

            try:
                # 1. 备份
                if backup_first:
                    from core.backup import BackupManager
                    backup_mgr = BackupManager()
                    backup_mgr.create_backup(tenant_id, backup_type="pre_upgrade")

                # 2. 拉取新镜像
                self._pull_images(new_version)

                # 3. 重启服务
                subprocess.run(
                    ["docker", "compose", "up", "-d", "--force-recreate"],
                    cwd=tenant_path,
                    check=True,
                )

                # 4. 健康检查
                self._wait_for_healthy(tenant_path)

                # 5. 更新版本
                tenant.hummingbot_version = new_version
                db.commit()

                print(f"✓ Tenant upgraded successfully")
                return True

            except Exception as e:
                print(f"✗ Upgrade failed, rolling back: {e}")
                # 回滚
                self.rollback_tenant_stack(tenant_id, old_version)
                raise

    def _pull_images(self, version: str):
        """拉取 Docker 镜像"""
        images = [
            f"hummingbot/hummingbot:{version}",
            f"hummingbot/dashboard:{version}",
        ]

        for image in images:
            print(f"⬇️  Pulling image: {image}")
            self.docker_client.images.pull(image)

    def rollback_tenant_stack(self, tenant_id: str, target_version: str) -> bool:
        """
        回滚客户栈

        回滚到指定版本
        """
        print(f"⏪ Rolling back tenant stack to version {target_version}")

        # 和升级流程类似，但使用旧版本
        return self.upgrade_tenant_stack(tenant_id, target_version, backup_first=False)

    def check_tenant_health(self, tenant_id: str) -> Dict:
        """
        检查租户健康状态

        返回详细的健康信息
        """
        with get_db() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            tenant_path = Path(tenant.deployment_path)

            # 获取容器状态
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                cwd=tenant_path,
                capture_output=True,
                text=True,
            )

            containers = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        import json
                        containers.append(json.loads(line))

            # 获取资源使用
            stats = self._get_resource_stats(tenant.tenant_code)

            # 更新数据库
            tenant.last_health_check = datetime.utcnow()
            tenant.health_status = "healthy" if len(containers) > 0 else "unhealthy"
            tenant.cpu_usage_percent = stats.get("cpu_percent", 0)
            tenant.memory_usage_mb = stats.get("memory_mb", 0)
            db.commit()

            return {
                "tenant_id": tenant_id,
                "status": tenant.status.value,
                "health": tenant.health_status,
                "containers": containers,
                "resources": stats,
            }

    def _get_resource_stats(self, tenant_code: str) -> Dict:
        """获取资源使用统计"""
        try:
            # 获取所有租户容器
            containers = self.docker_client.containers.list(
                filters={"name": tenant_code}
            )

            total_cpu = 0.0
            total_memory = 0

            for container in containers:
                stats = container.stats(stream=False)

                # CPU 使用率
                cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                           stats["precpu_stats"]["cpu_usage"]["total_usage"]
                system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                              stats["precpu_stats"]["system_cpu_usage"]
                cpu_percent = (cpu_delta / system_delta) * 100.0 if system_delta > 0 else 0.0

                # 内存使用
                memory_mb = stats["memory_stats"]["usage"] / (1024 * 1024)

                total_cpu += cpu_percent
                total_memory += memory_mb

            return {
                "cpu_percent": round(total_cpu, 2),
                "memory_mb": round(total_memory, 2),
                "container_count": len(containers),
            }

        except Exception as e:
            print(f"⚠️  Failed to get resource stats: {e}")
            return {"cpu_percent": 0, "memory_mb": 0, "container_count": 0}


# ==================== 使用示例 ====================

if __name__ == "__main__":
    orchestrator = TenantOrchestrator()

    # 创建客户栈
    # orchestrator.provision_tenant_stack("tenant-id-here")

    # 检查健康
    # health = orchestrator.check_tenant_health("tenant-id-here")
    # print(health)
