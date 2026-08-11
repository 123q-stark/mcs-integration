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
    
    # ===== 新增字段（B-01） =====
    requested_mode: str
    backup_soc_target: float
    # ============================
    
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyConfigUpdate(BaseModel):
    """策略配置更新请求模型（完整更新）"""
    config_name: str = Field(..., min_length=1, max_length=50)
    soc_min: float = Field(..., ge=0, le=100)
    soc_max: float = Field(..., ge=0, le=100)
    charge_power_kw: float = Field(..., gt=0, le=10)
    discharge_power_kw: float = Field(..., gt=0, le=10)
    
    # ===== 新增字段（B-01） =====
    requested_mode: str = Field(..., description="请求模式: AUTO/PV_PRIORITY/ECONOMIC_SCHEDULE/GRID_BACKUP/SAFE")
    backup_soc_target: float = Field(..., ge=0, le=100, description="备用SOC目标")
    # ============================

    @field_validator("soc_max")
    @classmethod
    def validate_soc_range(cls, v, info):
        """校验 soc_min < soc_max"""
        if "soc_min" in info.data and v <= info.data["soc_min"]:
            raise ValueError("soc_max must be greater than soc_min")
        return v

    @field_validator("backup_soc_target")
    @classmethod
    def validate_backup_soc(cls, v, info):
        """校验 backup_soc_target 必须在 soc_min 和 soc_max 之间"""
        soc_min = info.data.get("soc_min")
        soc_max = info.data.get("soc_max")
        if soc_min is not None and soc_max is not None:
            if not (soc_min <= v <= soc_max):
                raise ValueError(f"backup_soc_target ({v}) must be between soc_min ({soc_min}) and soc_max ({soc_max})")
        return v

    @field_validator("requested_mode")
    @classmethod
    def validate_requested_mode(cls, v):
        """校验 requested_mode 必须是有效枚举值"""
        valid_modes = ["AUTO", "PV_PRIORITY", "ECONOMIC_SCHEDULE", "GRID_BACKUP", "SAFE"]
        if v not in valid_modes:
            raise ValueError(f"requested_mode must be one of {valid_modes}, got {v}")
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

# ============ 电价配置 Schema ============

class PriceConfigResponse(BaseModel):
    """电价配置响应模型"""
    id: int
    valley_price: float
    flat_price: float
    peak_price: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceConfigUpdate(BaseModel):
    """电价配置更新请求模型"""
    valley_price: float | None = Field(None, ge=0, description="谷价 (CNY/kWh)")
    flat_price: float | None = Field(None, ge=0, description="平价 (CNY/kWh)")
    peak_price: float | None = Field(None, ge=0, description="峰价 (CNY/kWh)")


# ============ 电价配置 Schema ============

class PriceConfigResponse(BaseModel):
    """电价配置响应模型"""
    id: int
    valley_price: float
    flat_price: float
    peak_price: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceConfigUpdate(BaseModel):
    """电价配置更新请求模型"""
    valley_price: float | None = Field(None, ge=0, description="谷价 (CNY/kWh)")
    flat_price: float | None = Field(None, ge=0, description="平价 (CNY/kWh)")
    peak_price: float | None = Field(None, ge=0, description="峰价 (CNY/kWh)")


# ============ 电网策略配置 Schema（B-04） ============

class GridStrategyConfigResponse(BaseModel):
    """电网策略配置响应模型"""
    id: int
    max_import_power_kw: float
    allow_export: bool
    max_export_power_kw: float

    model_config = ConfigDict(from_attributes=True)


class GridStrategyConfigUpdate(BaseModel):
    """电网策略配置更新请求模型"""
    max_import_power_kw: float | None = Field(None, gt=0, description="最大购电功率 (kW)")
    allow_export: bool | None = Field(None, description="是否允许向电网送电")
    max_export_power_kw: float | None = Field(None, gt=0, description="最大上网功率 (kW)")
