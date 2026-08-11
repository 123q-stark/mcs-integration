"""
设备运行时状态 Schema
用于实时状态展示和历史数据
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DeviceRuntimeState(BaseModel):
    """设备实时运行状态（完整字段）"""
    device_code: str
    device_type: str
    timestamp: datetime
    is_online: bool
    quality: str = "good"  # good / stale / invalid / communication_error

    # 功率
    power_kw: float

    # 可选字段（不同类型设备有不同的字段）
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    temperature_c: Optional[float] = None
    energy_kwh: Optional[float] = None

    # 储能专用
    soc: Optional[float] = None
    soh: Optional[float] = None

    # 充电桩专用
    enabled: Optional[bool] = None
    status: Optional[str] = None  # idle / charging / disabled / fault
    connected: Optional[bool] = None  # 充电桩是否连接车辆

    # 储能告警
    alarm: bool = False