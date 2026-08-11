"""
设备策略配置数据库模型
为 PV001~PV005 和 CHG001~CHG005 建立策略视角的配置
"""
from sqlalchemy import Column, Integer, String, Boolean, Float
from app.database import Base


class StrategyDeviceConfigModel(Base):
    __tablename__ = "strategy_device_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_code = Column(String(20), unique=True, nullable=False, index=True)
    participate_in_strategy = Column(Boolean, default=True, nullable=False)
    allow_strategy_control = Column(Boolean, default=False, nullable=False)
    strategy_power_limit_kw = Column(Float, nullable=True)
    priority = Column(Integer, default=5, nullable=False)

    def __repr__(self):
        return f"<StrategyDeviceConfig(device={self.device_code}, participate={self.participate_in_strategy})>"
