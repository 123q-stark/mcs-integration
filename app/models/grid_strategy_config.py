"""
电网策略配置数据库模型
"""
from sqlalchemy import Column, Integer, Float, Boolean
from app.database import Base


class GridStrategyConfigModel(Base):
    __tablename__ = "grid_strategy_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    max_import_power_kw = Column(Float, default=300.0, nullable=False)
    allow_export = Column(Boolean, default=True, nullable=False)
    max_export_power_kw = Column(Float, default=100.0, nullable=False)

    def __repr__(self):
        return f"<GridStrategyConfig(import={self.max_import_power_kw}, export={self.max_export_power_kw})>"
