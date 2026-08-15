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
    source = Column(String(20), nullable=False)  # 'milp' or 'fixed_rule'
    status = Column(String(20), nullable=False)  # 'success' or 'failed'

    # ===== B-P0-07 新增：算法追溯字段 =====
    forecast_model_load = Column(String(50), nullable=True)   # 负荷预测模型名称
    forecast_model_pv = Column(String(50), nullable=True)     # PV预测模型名称
    optimizer_name = Column(String(50), nullable=True)        # 优化器名称
    algorithm_message = Column(Text, nullable=True)           # 算法消息
    execution_message = Column(Text, nullable=True)           # 执行消息
    # =====================================

    # JSON 字段存储预测和调度数据
    load_forecast_json = Column(Text, nullable=True)
    pv_forecast_json = Column(Text, nullable=True)
    schedule_json = Column(Text, nullable=True)

    def __repr__(self):
        return f"<StrategyRun(id={self.id}, mode={self.effective_mode}, status={self.status})>"
