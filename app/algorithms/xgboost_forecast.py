"""
XGBoost 次日负荷/PV预测器。
当历史不足7天时自动回退到基线（通过外部调用者处理，或内部 fallback）。
这里我们实现 XGBoost 训练和预测，但训练失败或数据不足时抛出异常，由 B 捕获并回退基线。
"""
import os
import pickle
import numpy as np
import pandas as pd
import xgboost as xgb
from datetime import datetime, timezone, timedelta
from typing import Optional

from .interfaces import LoadForecaster, PVForecaster
from .features import build_load_features, build_pv_features
from .model_store import ModelStore
from app.schemas.algorithm import ForecastResult, ForecastPoint


class XGBoostLoadForecaster(LoadForecaster):
    def __init__(
        self,
        model_store: Optional[ModelStore] = None,
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=2026,
        min_history_days=7
    ):
        self.model = None
        self.model_store = model_store or ModelStore()
        self.params = {
            'n_estimators': n_estimators,
            'max_depth': max_depth,
            'learning_rate': learning_rate,
            'subsample': subsample,
            'colsample_bytree': colsample_bytree,
            'random_state': random_state,
            'objective': 'reg:squarederror',
            'eval_metric': 'rmse'
        }
        self.min_history_days = min_history_days
        self.feature_names = None
        self.target = 'load'

    def fit(self, history: pd.DataFrame) -> None:
        """训练 XGBoost 模型"""
        if history.empty:
            raise ValueError("历史数据为空，无法训练")

        # 确保有足够历史
        days = (history['timestamp'].max() - history['timestamp'].min()).days
        if days < self.min_history_days:
            raise ValueError(f"历史数据不足 {self.min_history_days} 天，无法训练 XGBoost")

        # 构建特征
        df = build_load_features(history)
        # 目标列
        X = df.drop(columns=['timestamp', 'load_kw'])
        y = df['load_kw']
        self.feature_names = X.columns.tolist()

        # 训练
        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X, y)

        # 保存模型
        self.model_store.save_model(self.model, model_name=f"xgboost_load", meta={
            'target': 'load',
            'feature_names': self.feature_names,
            'trained_at': datetime.now(timezone.utc).isoformat(),
            'history_start': history['timestamp'].min().isoformat(),
            'history_end': history['timestamp'].max().isoformat()
        })

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime) -> ForecastResult:
        """预测次日96点"""
        # 如果模型未训练，尝试加载保存的模型
        if self.model is None:
            self.model = self.model_store.load_model("xgboost_load")
            if self.model is None:
                raise RuntimeError("模型未训练且无保存模型文件")

        # 构建用于预测的特征：我们需要最后几个时间点来构建滞后特征
        # 为了预测未来96点，我们需要从历史最后一天开始，逐点预测，因为滞后特征依赖前值
        # 方法：取历史最后96个点作为种子，然后滚动预测未来96点
        # 要求历史至少包含足够的数据（至少96+ lag所需）
        if len(history) < 100:
            raise ValueError("历史数据不足，无法构建预测特征")

        # 取最近96点作为起始种子
        seed = history.tail(96).copy()
        seed = seed.sort_values('timestamp').reset_index(drop=True)

        # 为了滚动预测，我们需要从最后一天开始，生成未来时间戳
        base_date = start_time.date()
        future_timestamps = [datetime(base_date.year, base_date.month, base_date.day, h, m)
                             for h in range(24) for m in [0,15,30,45]]

        # 构建一个扩展的DataFrame，包含种子和未来时间
        pred_df = seed[['timestamp']].copy()
        # 添加未来时间
        for ts in future_timestamps:
            pred_df = pd.concat([pred_df, pd.DataFrame([{'timestamp': ts}])], ignore_index=True)

        # 但我们还需要填充负荷值：前96个用真实值，后面未知，我们用预测值填充
        # 采用滚动预测：对每个未来点，利用已有的特征（包括滞后）预测
        # 我们需要构建特征，但滞后值可能缺失，我们用最近值填充
        # 方法：把种子和未来合并，然后构建特征，但未来滞后值我们用前向填充
        # 先合并
        all_df = pd.concat([seed, pd.DataFrame({'timestamp': future_timestamps})], ignore_index=True)
        all_df = all_df.sort_values('timestamp').reset_index(drop=True)

        # 暂时用0填充load_kw列（对预测点）
        all_df['load_kw'] = seed['load_kw'].tolist() + [np.nan]*96

        # 构建特征（此时未来点的load_kw为NaN，但我们可以用滞后值填充）
        # 先构建时间特征（不依赖load_kw）
        all_df['hour'] = all_df['timestamp'].dt.hour
        all_df['minute_slot'] = all_df['timestamp'].dt.minute // 15
        all_df['weekday'] = all_df['timestamp'].dt.weekday
        all_df['is_weekend'] = all_df['weekday'].isin([5, 6]).astype(int)

        # 滞后特征：需要用load_kw的前值，但我们还没有未来预测值，所以用滚动预测
        # 我们将按顺序预测未来点，每预测一个，更新load_kw，然后用于后续
        # 简化：先获取种子最后一部分来构建初始滞后
        # 更简单的方法：使用所有历史数据来训练，但预测时输入必须包含未来时刻的特征（除了负荷）
        # 可以直接用最后96个点作为输入，预测第一个未来点，然后更新。
        # 实现一个循环：
        # 初始化一个list存放预测结果
        predictions = []
        current_history = seed.copy()  # 包含真实值

        # 对每个未来时间点：
        for i, ts in enumerate(future_timestamps):
            # 构建当前可用的特征：使用current_history（包含真实+已预测）
            # 为了构建特征，我们需要最近的数据
            # 取最近足够的行（至少 lag_96 等）
            # 这里简化：我们使用整个current_history，并构建特征函数
            # 但为了速度，我们只取最近96+4个点
            if len(current_history) >= 100:
                recent = current_history.tail(100)
            else:
                recent = current_history

            # 构建特征（包括滞后），注意此时预测点还没有load_kw，我们暂时设为0，但滞后值应该使用真实/预测值
            # 我们需要复制recent，添加一行新记录（未来时间，load_kw未知）
            # 为了构建特征，我们首先将新点加入recent并计算滞后
            # 因为我们只能预测一个点，所以先复制recent，添加一行新点，load_kw=0，然后构建特征，预测后替换
            # 但滞后需要前值，所以新点的滞后值会从recent最后一行取得
            # 更简单：单独构建特征向量
            # 从recent中提取最后几个值
            last = recent.iloc[-1]
            # 构建新行特征
            new_row = {
                'timestamp': ts,
                'hour': ts.hour,
                'minute_slot': ts.minute // 15,
                'weekday': ts.weekday(),
                'is_weekend': 1 if ts.weekday() >= 5 else 0,
                'lag_1': last['load_kw'] if len(recent) >= 1 else 0,
                'lag_4': recent.iloc[-4]['load_kw'] if len(recent) >= 4 else 0,
                'lag_96': recent.iloc[-96]['load_kw'] if len(recent) >= 96 else 0,
                'rolling_mean_4': recent['load_kw'].rolling(4, min_periods=1).mean().iloc[-1],
                'rolling_mean_96': recent['load_kw'].rolling(96, min_periods=1).mean().iloc[-1],
            }
            # 转为DataFrame
            X_new = pd.DataFrame([new_row])
            # 确保列顺序与训练时一致
            X_new = X_new[self.feature_names]
            # 预测
            pred = self.model.predict(X_new)[0]
            predictions.append(pred)

            # 将预测值加入current_history（作为新行）
            new_row_full = new_row.copy()
            new_row_full['load_kw'] = pred
            new_row_full['timestamp'] = ts
            current_history = pd.concat([current_history, pd.DataFrame([new_row_full])], ignore_index=True)

        # 构建结果
        points = []
        for ts, val in zip(future_timestamps, predictions):
            points.append(ForecastPoint(timestamp=ts, value_kw=float(max(val, 0.0))))

        return ForecastResult(
            model_name="XGBoostLoad",
            target="load",
            created_at=datetime.now(timezone.utc),
            step_minutes=15,
            points=points,
            mae=None,
            rmse=None
        )


class XGBoostPVForecaster(PVForecaster):
    """类似，但针对PV，特征使用build_pv_features，预测值非负裁剪"""
    def __init__(
        self,
        model_store: Optional[ModelStore] = None,
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=2026,
        min_history_days=7
    ):
        self.model = None
        self.model_store = model_store or ModelStore()
        self.params = {
            'n_estimators': n_estimators,
            'max_depth': max_depth,
            'learning_rate': learning_rate,
            'subsample': subsample,
            'colsample_bytree': colsample_bytree,
            'random_state': random_state,
            'objective': 'reg:squarederror',
            'eval_metric': 'rmse'
        }
        self.min_history_days = min_history_days
        self.feature_names = None
        self.target = 'pv'

    def fit(self, history: pd.DataFrame) -> None:
        if history.empty:
            raise ValueError("历史数据为空")
        days = (history['timestamp'].max() - history['timestamp'].min()).days
        if days < self.min_history_days:
            raise ValueError(f"历史不足 {self.min_history_days} 天")

        df = build_pv_features(history)
        X = df.drop(columns=['timestamp', 'pv_kw'])
        y = df['pv_kw']
        self.feature_names = X.columns.tolist()

        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X, y)

        self.model_store.save_model(self.model, model_name="xgboost_pv", meta={
            'target': 'pv',
            'feature_names': self.feature_names,
            'trained_at': datetime.now(timezone.utc).isoformat(),
            'history_start': history['timestamp'].min().isoformat(),
            'history_end': history['timestamp'].max().isoformat()
        })

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime) -> ForecastResult:
        if self.model is None:
            self.model = self.model_store.load_model("xgboost_pv")
            if self.model is None:
                raise RuntimeError("未找到PV模型")

        # 类似Load的滚动预测，但使用pv_kw列
        seed = history.tail(96).copy()
        seed = seed.sort_values('timestamp').reset_index(drop=True)

        base_date = start_time.date()
        future_timestamps = [datetime(base_date.year, base_date.month, base_date.day, h, m)
                             for h in range(24) for m in [0,15,30,45]]

        current_history = seed.copy()
        predictions = []
        for ts in future_timestamps:
            recent = current_history.tail(100)
            # 构建特征
            last = recent.iloc[-1]
            new_row = {
                'timestamp': ts,
                'hour': ts.hour,
                'minute_slot': ts.minute // 15,
                'sin_time': np.sin(2 * np.pi * (ts.hour + ts.minute/60) / 24),
                'cos_time': np.cos(2 * np.pi * (ts.hour + ts.minute/60) / 24),
                'lag_96': recent.iloc[-96]['pv_kw'] if len(recent) >= 96 else 0,
                'rolling_mean_96': recent['pv_kw'].rolling(96, min_periods=1).mean().iloc[-1],
            }
            X_new = pd.DataFrame([new_row])
            X_new = X_new[self.feature_names]
            pred = self.model.predict(X_new)[0]
            pred = max(pred, 0.0)  # 非负
            predictions.append(pred)

            new_row_full = new_row.copy()
            new_row_full['pv_kw'] = pred
            new_row_full['timestamp'] = ts
            current_history = pd.concat([current_history, pd.DataFrame([new_row_full])], ignore_index=True)

        points = []
        for ts, val in zip(future_timestamps, predictions):
            points.append(ForecastPoint(timestamp=ts, value_kw=float(val)))

        return ForecastResult(
            model_name="XGBoostPV",
            target="pv",
            created_at=datetime.now(timezone.utc),
            step_minutes=15,
            points=points,
            mae=None,
            rmse=None
        )