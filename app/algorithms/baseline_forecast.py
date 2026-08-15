"""
历史同slot基线预测：用最近 N 天同一时刻的平均值作为预测。
"""
from typing import List
from datetime import datetime, timezone, timedelta
import pandas as pd

from .interfaces import LoadForecaster, PVForecaster
from app.schemas.algorithm import ForecastResult, ForecastPoint


class HistoricalSameSlotBaseline(LoadForecaster, PVForecaster):
    """同时实现负荷和PV基线，内部使用相同逻辑"""

    def __init__(self, n_days: int = 7):
        self.n_days = n_days
        self.target = None  # 'load' or 'pv'

    def fit(self, history: pd.DataFrame) -> None:
        # 基线不需要训练，但为了接口一致，留空
        pass

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime, target: str) -> ForecastResult:
        """
        target: 'load' 或 'pv'
        history 必须包含列 timestamp 和对应的目标列（load_kw 或 pv_kw）
        """
        # 确定目标列名
        if target == 'load':
            target_col = 'load_kw'
        elif target == 'pv':
            target_col = 'pv_kw'
        else:
            raise ValueError("target must be 'load' or 'pv'")

        # 提取最近 n_days 天数据
        end = history['timestamp'].max()
        start = end - timedelta(days=self.n_days)
        recent = history[history['timestamp'] >= start].copy()
        if recent.empty:
            # 如果历史不足，使用所有历史
            recent = history.copy()

        # 为每个时刻（0~95）计算平均
        # 将时间对齐到15分钟槽位
        recent['slot'] = (recent['timestamp'].dt.hour * 4 + recent['timestamp'].dt.minute // 15).astype(int)

        # 按 slot 分组求均值
        means = recent.groupby('slot')[target_col].mean().reindex(range(96), fill_value=0.0)

        # 生成预测点
        base_date = start_time.date()
        points = []
        for slot in range(96):
            dt = datetime(base_date.year, base_date.month, base_date.day, slot//4, (slot%4)*15)
            points.append(ForecastPoint(
                timestamp=dt,
                value_kw=float(means.iloc[slot])
            ))

        # 确保非负
        for p in points:
            if p.value_kw < 0:
                p.value_kw = 0.0

        return ForecastResult(
            model_name=f"HistoricalSameSlotBaseline_{target}",
            target=target,
            created_at=datetime.now(timezone.utc),
            step_minutes=15,
            points=points,
            mae=None,
            rmse=None
        )