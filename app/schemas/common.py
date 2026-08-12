from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SystemState(BaseModel):
    """设备层向策略层提供的统一系统状态。"""

    timestamp: datetime
    simulated_hour: float
    pv_power: float
    load_power: float
    storage_power: float
    storage_soc: float


class ControlDecision(BaseModel):
    """策略层向执行层提供的统一控制决策。"""

    storage_power_target: float
    action: str
    message: str
    created_at: datetime
    source: str = "fixed_rule"
    mode: str = "PV_PRIORITY"
    decision_id: str | None = None
    charger_targets: list[dict] = []


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


class ControlExecutionResult(BaseModel):
    """控制执行结果"""
    decision_id: str | None = None
    success: bool
    storage_power_actual_kw: float
    charger_results: list[dict] = []
    message: str
    executed_at: datetime
