"""
算法模块公共 Schema
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class ForecastPoint(BaseModel):
    timestamp: datetime
    value_kw: float


class ForecastResult(BaseModel):
    # P0-01: 新增 available 字段，表示预测是否有效
    available: bool = True
    model_name: str
    target: str  # 'load' or 'pv'
    created_at: datetime
    step_minutes: int = 15
    points: List[ForecastPoint]
    mae: Optional[float] = None
    rmse: Optional[float] = None
    message: Optional[str] = None  # P0-01: 当 available=False 时说明原因

class SchedulePoint(BaseModel):
    timestamp: datetime
    storage_power_target_kw: float
    predicted_soc: float


class OptimizationResult(BaseModel):
    optimizer_name: str
    created_at: datetime
    success: bool
    objective_value: Optional[float] = None
    schedule: List[SchedulePoint]
    message: str
