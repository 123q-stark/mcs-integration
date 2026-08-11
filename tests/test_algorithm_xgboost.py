import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.algorithms.xgboost_forecast import XGBoostLoadForecaster, XGBoostPVForecaster

def test_xgboost_load():
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*10)]
    # 模拟日周期负荷
    load_data = [50 + 30*np.sin(2*np.pi*i/96) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': load_data})

    forecaster = XGBoostLoadForecaster(min_history_days=7)
    forecaster.fit(df)
    result = forecaster.predict_next_day(df, base + timedelta(days=10))
    assert len(result.points) == 96
    assert all(p.value_kw >= 0 for p in result.points)
    print("XGBoost负荷预测测试通过")

def test_xgboost_pv():
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*10)]
    # 模拟日间光伏
    pv_data = [max(0, 100*np.sin(np.pi*(i%96)/96)) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'pv_kw': pv_data})

    forecaster = XGBoostPVForecaster(min_history_days=7)
    forecaster.fit(df)
    result = forecaster.predict_next_day(df, base + timedelta(days=10))
    assert len(result.points) == 96
    assert all(p.value_kw >= 0 for p in result.points)
    print("XGBoost光伏预测测试通过")