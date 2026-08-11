# app/models/__init__.py
"""
数据库模型包
为了保持向后兼容，所有模型统一从本包导出
"""
from .system import Base, SystemHistory, ControlCommand, DeviceHistory  # ← 新增 DeviceHistory
from .device import Device
from .strategy import StrategyConfigModel

__all__ = [
    "Base",
    "SystemHistory",
    "ControlCommand",
    "DeviceHistory",  # ← 新增
    "Device",
    "StrategyConfigModel",
]