"""
算法模块入口
暴露主要类给 B 的 AlgorithmBridgeService 调用。
"""
from .interfaces import LoadForecaster, PVForecaster, EnergyOptimizer, AutoModeSelector
from .baseline_forecast import HistoricalSameSlotBaseline
from .xgboost_forecast import XGBoostLoadForecaster, XGBoostPVForecaster
from .milp_dispatch import MilpBatteryOptimizer
from .auto_mode import AutoModeSelectorRule
from .model_store import ModelStore

__all__ = [
    "LoadForecaster",
    "PVForecaster",
    "EnergyOptimizer",
    "AutoModeSelector",
    "HistoricalSameSlotBaseline",
    "XGBoostLoadForecaster",
    "XGBoostPVForecaster",
    "MilpBatteryOptimizer",
    "AutoModeSelectorRule",
    "ModelStore",
]