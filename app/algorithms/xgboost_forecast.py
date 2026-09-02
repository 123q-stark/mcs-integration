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
from datetime import datetime, timedelta
from typing import Optional

from .interfaces import LoadForecaster, PVForecaster
from .features import build_load_features, build_pv_features
from .model_store import ModelStore
from .evaluation import mae, rmse  # P1-06 新增
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
        # P1-06: 存储验证集指标
        self._mae = None
        self._rmse = None

    def fit(self, history: pd.DataFrame) -> None:
        """
        训练 XGBoost 模型
        P0-04: 使用修复后的 features.py（shift(1) 避免泄漏）
        P1-06: 使用时间顺序 hold-out 计算 MAE/RMSE
        P1-07: 保存完整元数据
        """
        if history.empty:
            raise ValueError("历史数据为空，无法训练")

        # 确保有足够历史
        days = (history['timestamp'].max() - history['timestamp'].min()).days
        if days < self.min_history_days:
            raise ValueError(f"历史数据不足 {self.min_history_days} 天，无法训练 XGBoost")

        # 构建特征（P0-04: 使用修复后的 features.py）
        df = build_load_features(history)
        X = df.drop(columns=['timestamp', 'load_kw'])
        y = df['load_kw']
        self.feature_names = X.columns.tolist()

        # P1-06: 时间顺序 hold-out（前80%训练，后20%验证）
        split_idx = int(len(df) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        # 训练
        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X_train, y_train)

        # P1-06: 计算验证集 MAE/RMSE
        y_pred = self.model.predict(X_val)
        self._mae = mae(y_val.tolist(), y_pred.tolist())
        self._rmse = rmse(y_val.tolist(), y_pred.tolist())

        # P1-07: 保存模型时包含完整元数据
        self.model_store.save_model(self.model, model_name=f"xgboost_load", meta={
            'target': 'load',
            'feature_names': self.feature_names,
            'trained_at': datetime.utcnow().isoformat(),
            'history_start': history['timestamp'].min().isoformat(),
            'history_end': history['timestamp'].max().isoformat(),
            'feature_version': 'v1.7',  # P1-07 新增
            'metrics': {                # P1-07 新增
                'mae': self._mae,
                'rmse': self._rmse
            }
        })

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime) -> ForecastResult:
        """预测次日96点"""
        # 如果模型未训练，尝试加载保存的模型
        if self.model is None:
            self.model = self.model_store.load_model("xgboost_load")
            if self.model is None:
                raise RuntimeError("模型未训练且无保存模型文件")
            # 尝试加载元数据获取指标
            meta = self.model_store.load_meta("xgboost_load")
            if meta and 'metrics' in meta:
                self._mae = meta['metrics'].get('mae')
                self._rmse = meta['metrics'].get('rmse')

        # 构建用于预测的特征：我们需要最后几个时间点来构建滞后特征
        # 为了预测未来96点，我们需要从历史最后一天开始，逐点预测
        if len(history) < 100:
            raise ValueError("历史数据不足，无法构建预测特征")

        # 取最近96点作为起始种子
        seed = history.tail(96).copy()
        seed = seed.sort_values('timestamp').reset_index(drop=True)

        base_date = start_time.date()
        future_timestamps = [datetime(base_date.year, base_date.month, base_date.day, h, m)
                             for h in range(24) for m in [0, 15, 30, 45]]

        current_history = seed.copy()
        predictions = []

        for ts in future_timestamps:
            recent = current_history.tail(100)
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
                # P0-04: 使用 shift(1) 后的滚动均值（已由 features.py 保证）
                'rolling_mean_4': recent['load_kw'].rolling(4, min_periods=1).mean().iloc[-1],
                'rolling_mean_96': recent['load_kw'].rolling(96, min_periods=1).mean().iloc[-1],
            }
            X_new = pd.DataFrame([new_row])
            X_new = X_new[self.feature_names]
            pred = self.model.predict(X_new)[0]
            predictions.append(pred)

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
            created_at=datetime.utcnow(),
            step_minutes=15,
            points=points,
            mae=self._mae,    # P1-06 新增
            rmse=self._rmse   # P1-06 新增
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
        # P1-06: 存储验证集指标
        self._mae = None
        self._rmse = None

    def fit(self, history: pd.DataFrame) -> None:
        """
        训练 XGBoost PV 模型
        P0-04: 使用修复后的 features.py
        P1-06: 时间顺序 hold-out 计算 MAE/RMSE
        P1-07: 保存完整元数据
        """
        if history.empty:
            raise ValueError("历史数据为空")
        days = (history['timestamp'].max() - history['timestamp'].min()).days
        if days < self.min_history_days:
            raise ValueError(f"历史不足 {self.min_history_days} 天")

        df = build_pv_features(history)
        X = df.drop(columns=['timestamp', 'pv_kw'])
        y = df['pv_kw']
        self.feature_names = X.columns.tolist()

        # P1-06: 时间顺序 hold-out
        split_idx = int(len(df) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X_train, y_train)

        # P1-06: 计算验证集 MAE/RMSE
        y_pred = self.model.predict(X_val)
        self._mae = mae(y_val.tolist(), y_pred.tolist())
        self._rmse = rmse(y_val.tolist(), y_pred.tolist())

        # P1-07: 保存模型时包含完整元数据
        self.model_store.save_model(self.model, model_name="xgboost_pv", meta={
            'target': 'pv',
            'feature_names': self.feature_names,
            'trained_at': datetime.utcnow().isoformat(),
            'history_start': history['timestamp'].min().isoformat(),
            'history_end': history['timestamp'].max().isoformat(),
            'feature_version': 'v1.7',  # P1-07 新增
            'metrics': {                # P1-07 新增
                'mae': self._mae,
                'rmse': self._rmse
            }
        })

    def predict_next_day(self, history: pd.DataFrame, start_time: datetime) -> ForecastResult:
        if self.model is None:
            self.model = self.model_store.load_model("xgboost_pv")
            if self.model is None:
                raise RuntimeError("未找到PV模型")
            meta = self.model_store.load_meta("xgboost_pv")
            if meta and 'metrics' in meta:
                self._mae = meta['metrics'].get('mae')
                self._rmse = meta['metrics'].get('rmse')

        seed = history.tail(96).copy()
        seed = seed.sort_values('timestamp').reset_index(drop=True)

        base_date = start_time.date()
        future_timestamps = [datetime(base_date.year, base_date.month, base_date.day, h, m)
                             for h in range(24) for m in [0, 15, 30, 45]]

        current_history = seed.copy()
        predictions = []

        for ts in future_timestamps:
            recent = current_history.tail(100)
            last = recent.iloc[-1]

            new_row = {
                'timestamp': ts,
                'hour': ts.hour,
                'minute_slot': ts.minute // 15,
                'sin_time': np.sin(2 * np.pi * (ts.hour + ts.minute/60) / 24),
                'cos_time': np.cos(2 * np.pi * (ts.hour + ts.minute/60) / 24),
                'lag_96': recent.iloc[-96]['pv_kw'] if len(recent) >= 96 else 0,
                # P0-04: 使用 shift(1) 后的滚动均值
                'rolling_mean_96': recent['pv_kw'].rolling(96, min_periods=1).mean().iloc[-1],
            }
            X_new = pd.DataFrame([new_row])
            X_new = X_new[self.feature_names]
            pred = self.model.predict(X_new)[0]
            pred = max(pred, 0.0)
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
            created_at=datetime.utcnow(),
            step_minutes=15,
            points=points,
            mae=self._mae,    # P1-06 新增
            rmse=self._rmse   # P1-06 新增
        )