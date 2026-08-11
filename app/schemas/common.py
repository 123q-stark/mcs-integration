from __future__ import annotations

from datetime import datetime
from typing import Optional

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


class ControlDecision(BaseModel):
    """策略层向执行层提供的统一控制决策。"""

    storage_power_target: float
    action: str
    message: str
    created_at: datetime


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