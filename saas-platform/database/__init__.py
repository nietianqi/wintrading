"""
Database initialization and connection management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os

from .models import Base

# 数据库连接配置
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/hummingbot_saas"
)

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 连接前检查
    echo=False,  # 生产环境关闭 SQL 日志
)

# Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """初始化数据库（创建所有表）"""
    Base.metadata.create_all(bind=engine)
    print("✓ Database initialized successfully")


def drop_database():
    """删除所有表（危险操作，仅用于开发）"""
    Base.metadata.drop_all(bind=engine)
    print("✗ All tables dropped")


@contextmanager
def get_db() -> Session:
    """
    获取数据库会话（上下文管理器）

    使用示例：
    with get_db() as db:
        user = db.query(User).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session():
    """
    获取数据库会话（FastAPI 依赖注入）

    使用示例：
    @app.get("/users")
    def get_users(db: Session = Depends(get_db_session)):
        return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
