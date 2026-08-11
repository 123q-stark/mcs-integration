"""
策略配置数据库模型
"""
from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StrategyConfigModel(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    soc_min: Mapped[float] = mapped_column(Float, nullable=False)
    soc_max: Mapped[float] = mapped_column(Float, nullable=False)
    charge_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    discharge_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # ===== 新增字段（B-01） =====
    requested_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="AUTO")
    backup_soc_target: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    # ============================
    
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<StrategyConfig(id={self.id}, name={self.config_name}, active={self.is_active}, mode={self.requested_mode})>"