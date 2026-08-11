"""
算法接口协议（Protocol），定义预测、优化、模式选择的标准方法。
所有算法类必须实现这些协议，以便 B 通过 AlgorithmBridgeService 调用。
"""
from typing import Protocol, List, Optional
from datetime import datetime
import pandas as pd

# 从公共 Schema 导入（已修正为 algorithm 子模块）
from app.schemas.algorithm import ForecastResult, OptimizationResult


class LoadForecaster(Protocol):
    """负荷预测器协议"""

    def fit(self, history: pd.DataFrame) -> None:
        """
        训练/拟合模型（如果模型需要训练）
        history 必须包含列：timestamp, load_kw, 以及其他特征（由 features.py 生成）
        """
        ...

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime) -> ForecastResult:
        """
        预测次日 96 点负荷
        history: 用于预测的历史数据（至少包含最近几天）
        start_time: 次日开始时间（通常为当天 00:00 + 1天）
        返回 ForecastResult（96点）
        """
        ...


class PVForecaster(Protocol):
    """光伏预测器协议（同 LoadForecaster）"""

    def fit(self, history: pd.DataFrame) -> None:
        ...

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime) -> ForecastResult:
        ...


class EnergyOptimizer(Protocol):
    """储能调度优化器协议"""

    def optimize(self, request: dict) -> OptimizationResult:
        """
        request 应包含：
            load_forecast: List[float]  # 96点
            pv_forecast: List[float]    # 96点
            price_series: List[float]   # 96点
            current_soc: float
            battery_capacity_kwh: float
            soc_min: float
            soc_max: float
            charge_power_max: float     # 正值，充电功率上限（绝对值）
            discharge_power_max: float  # 正值，放电功率上限（绝对值）
            max_import_power: float     # 最大购电功率
            allow_export: bool
            max_export_power: float     # 若允许售电，最大售电功率
        """
        ...


class AutoModeSelector(Protocol):
    """AUTO模式推荐协议"""

    def select(self, context: dict) -> str:
        """
        context 包含当前系统状态和可用算法状态，例如：
            current_soc: float
            backup_soc_target: float
            forecast_available: bool
            schedule_available: bool
            any_device_error: bool
            current_price_level: str  # 'peak'/'flat'/'valley'
            pv_power: float
            load_power: float
            等等
        返回推荐模式（字符串，必须属于冻结的枚举：PV_PRIORITY, ECONOMIC_SCHEDULE, GRID_BACKUP, AUTO, SAFE）
        """
        ...