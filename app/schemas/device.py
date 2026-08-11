from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DeviceSummary(BaseModel):
    """设备列表摘要（用于 GET /api/devices）"""
    id: int
    device_code: str
    device_name: str
    device_type: str
    is_online: bool
    rated_power_kw: Optional[float] = None
    updated_at: datetime


class DeviceDetail(BaseModel):
    """设备详情（用于 GET /api/devices/{device_id}）"""
    id: int
    device_code: str
    device_name: str
    device_type: str
    is_online: bool
    rated_power_kw: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class DeviceStatusResponse(BaseModel):
    """设备实时状态（用于 GET /api/devices/{device_id}/status）"""
    device_id: int
    device_code: str
    device_type: str
    is_online: bool
    power_kw: float
    storage_soc: Optional[float] = None
    updated_at: datetime