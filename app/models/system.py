from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemHistory(Base):
    __tablename__ = "system_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    pv_power: Mapped[float] = mapped_column(Float)
    load_power: Mapped[float] = mapped_column(Float)
    storage_power: Mapped[float] = mapped_column(Float)
    storage_soc: Mapped[float] = mapped_column(Float)


class ControlCommand(Base):
    __tablename__ = "control_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    command_value: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(32))
    strategy_message: Mapped[str] = mapped_column(Text)
    execute_result: Mapped[str] = mapped_column(String(32))


# ===== 新增：设备历史记录模型 =====
class DeviceHistory(Base):
    """设备历史记录（用于曲线展示）"""
    __tablename__ = "device_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    device_code: Mapped[str] = mapped_column(String(50), nullable=False)
    device_type: Mapped[str] = mapped_column(String(30), nullable=False)
    power_kw: Mapped[float] = mapped_column(Float, nullable=True)
    storage_soc: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=datetime.now)