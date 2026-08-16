from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    """集中管理 SQLAlchemy 引擎和数据库会话。"""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

        if database_url.startswith("sqlite:///"):
            db_path = Path(database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        # ===== 添加超时参数，避免数据库锁 =====
        connect_args = {"check_same_thread": False}
        if database_url.startswith("sqlite"):
            connect_args["timeout"] = 30  # 等待锁释放最多 30 秒

        self.engine = create_engine(database_url, connect_args=connect_args)

        # ===== 启用 WAL 模式，提高并发性能 =====
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if database_url.startswith("sqlite"):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")  # 30 秒超时（毫秒）
                cursor.close()

        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    def create_tables(self) -> None:
        # 导入模型，确保 SQLAlchemy 已注册所有表。
        from app import models  # noqa: F401

        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()