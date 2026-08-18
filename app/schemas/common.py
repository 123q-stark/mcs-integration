from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class SystemState(BaseModel):
    """设备层向策略层提供的统一系统状态。"""

    # ===== v1.0 兼容字段 =====
    timestamp: datetime
    simulated_hour: float
    pv_power: float
    load_power: float
    storage_power: float
    storage_soc: float

    # ===== v1.1 扩展字段 =====
    grid_power: float = 0.0
    pv_units: list = Field(default_factory=list)
    chargers: list = Field(default_factory=list)
    battery: Optional[dict] = None
    grid: Optional[dict] = None


# ===== A-8 新增：ChargerTarget =====
class ChargerTarget(BaseModel):
    """充电桩控制目标（03 冻结契约）"""
    device_code: str
    enabled: Optional[bool] = None
    power_limit_kw: Optional[float] = None


# ===== A-8 修改：补充完整字段 =====
class ControlDecision(BaseModel):
    """策略层向执行层提供的统一控制决策（03 冻结契约）"""
    storage_power_target: float
    action: str
    message: str
    created_at: datetime
    source: str = "fixed_rule"           # fixed_rule / milp / auto
    mode: str = "PV_PRIORITY"
    decision_id: Optional[str] = None
    charger_targets: List[ChargerTarget] = []


# ===== A-8 新增：ControlExecutionResult =====
class ControlExecutionResult(BaseModel):
    """执行层返回的控制执行结果（03 冻结契约）"""
    decision_id: Optional[str] = None
    success: bool
    storage_power_actual_kw: float
    charger_results: List[dict] = []
    message: str
    executed_at: datetime


# ===== A 公共文件修改：新增 ManualDeviceControl =====
class ManualDeviceControl(BaseModel):
    """手动设备控制命令（03 冻结契约）"""
    device_code: str
    command: Literal["start", "stop", "set_power"]
    target_power_kw: Optional[float] = None


class StatusResponse(BaseModel):
    pv_power: float
    load_power: float
    storage_power: float
    storage_soc: float
    action: str
    strategy_message: str
    updated_at: datetime


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    pv_power: float
    load_power: float
    storage_power: float
    storage_soc: float


class CommandItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    command_value: float
    action: str
    strategy_message: str
    execute_result: str


class ResetResponse(BaseModel):
    success: bool
    message: str