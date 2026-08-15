"""
设备运行时状态 Schema
用于实时状态展示和历史数据
"""
from datetime import datetime
from typing import Optional, List
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

    # A-P1-02: 额定功率（物理限幅用）
    rated_power_kw: Optional[float] = None

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


class SystemState(BaseModel):
    """完整站点系统状态（聚合 + 设备明细）"""
    timestamp: datetime
    simulated_hour: float

    # 聚合字段（v1.0 原有兼容字段）
    pv_power: float          # 5路PV之和
    load_power: float        # 5个Charger之和
    storage_power: float     # Battery功率（正放负充）
    storage_soc: float       # Battery SOC

    # v1.1 新增扩展字段（03_冻结契约要求）
    grid_power: float                              # 正购负售
    pv_units: List[DeviceRuntimeState] = []        # 5个PV独立状态
    chargers: List[DeviceRuntimeState] = []        # 5个Charger独立状态
    battery: Optional[DeviceRuntimeState] = None   # Battery独立状态
    grid: Optional[DeviceRuntimeState] = None      # Grid独立状态