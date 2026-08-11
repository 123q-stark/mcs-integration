# app/schemas/strategy.py
"""
策略配置 Pydantic Schema
包含请求、响应和预览模型
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============ 策略配置 Schema ============

class StrategyConfigResponse(BaseModel):
    """策略配置响应模型"""
    id: int
    config_name: str
    soc_min: float
    soc_max: float
    charge_power_kw: float
    discharge_power_kw: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)  # ← B-RC2-04


class StrategyConfigUpdate(BaseModel):
    """策略配置更新请求模型（完整更新）"""
    config_name: str = Field(..., min_length=1, max_length=50)
    soc_min: float = Field(..., ge=0, le=100)
    soc_max: float = Field(..., ge=0, le=100)
    charge_power_kw: float = Field(..., gt=0, le=10)      # ← B-RC2-02
    discharge_power_kw: float = Field(..., gt=0, le=10)   # ← B-RC2-02


    @field_validator("soc_max")
    @classmethod
    def validate_soc_range(cls, v, info):
        """校验 soc_min < soc_max"""
        if "soc_min" in info.data and v <= info.data["soc_min"]:
            raise ValueError("soc_max must be greater than soc_min")
        return v


# ============ 策略预览 Schema ============

class StrategyPreviewRequest(BaseModel):
    """策略预览请求模型"""
    pv_power: float = Field(..., description="光伏功率 (kW)")
    load_power: float = Field(..., description="负载功率 (kW)")
    storage_power: float = Field(..., description="当前储能功率 (kW)")
    storage_soc: float = Field(..., ge=0, le=100, description="储能 SOC (0-100)")


class StrategyPreviewResponse(BaseModel):
    """策略预览响应模型"""
    storage_power_target: float = Field(..., description="储能目标功率，正=放电，负=充电")
    action: str = Field(..., description="动作: charge/discharge/idle")
    message: str = Field(..., description="策略判断说明")
    created_at: datetime = Field(..., description="决策时间")