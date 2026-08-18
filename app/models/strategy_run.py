"""
策略运行记录数据库模型（B-10）
保存每次策略运行的完整信息
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from app.database import Base


class StrategyRunModel(Base):
    __tablename__ = "strategy_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    requested_mode = Column(String(20), nullable=False)
    effective_mode = Column(String(20), nullable=False)
    fallback_used = Column(Boolean, default=False, nullable=False)
    storage_power_target = Column(Float, nullable=False)
    action = Column(String(20), nullable=False)
    message = Column(Text, nullable=True)
    source = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)

    # ===== v1.6 追溯字段 =====
    forecast_model_load = Column(String(50), nullable=True)
    forecast_model_pv = Column(String(50), nullable=True)
    optimizer_name = Column(String(50), nullable=True)
    algorithm_message = Column(Text, nullable=True)
    execution_message = Column(Text, nullable=True)

    # JSON 字段
    load_forecast_json = Column(Text, nullable=True)
    pv_forecast_json = Column(Text, nullable=True)
    schedule_json = Column(Text, nullable=True)

    def __repr__(self):
        return f"<StrategyRun(id={self.id}, mode={self.effective_mode}, status={self.status})>"
