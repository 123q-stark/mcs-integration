"""
设备遥测历史模型
每15分钟每个逻辑设备保存一条遥测记录
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from app.database import Base


class DeviceTelemetry(Base):
    __tablename__ = "device_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    device_code = Column(String(50), nullable=False, index=True)
    device_type = Column(String(30), nullable=False, index=True)

    # 功率（所有设备都有）
    power_kw = Column(Float, nullable=False, default=0.0)

    # 可选字段（不同类型设备有不同字段）
    voltage_v = Column(Float, nullable=True)
    current_a = Column(Float, nullable=True)
    temperature_c = Column(Float, nullable=True)
    energy_kwh = Column(Float, nullable=True)

    # 储能专用
    soc = Column(Float, nullable=True)
    soh = Column(Float, nullable=True)

    # 充电桩专用
    enabled = Column(Boolean, nullable=True)
    status = Column(String(30), nullable=True)

    # 质量
    quality = Column(String(30), nullable=False, default="good")

    def __repr__(self):
        return f"<DeviceTelemetry(device_code='{self.device_code}', created_at='{self.created_at}')>"