import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.algorithms.baseline_forecast import HistoricalSameSlotBaseline
from app.algorithms.xgboost_forecast import XGBoostLoadForecaster, XGBoostPVForecaster
from app.algorithms.milp_dispatch import MilpBatteryOptimizer

def test_contract_baseline():
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*10)]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': [50+10*(i%24) for i in range(len(timestamps))]})
    forecaster = HistoricalSameSlotBaseline(n_days=7)
    result = forecaster.predict_next_day(df, base + timedelta(days=10), target='load')
    assert len(result.points) == 96
    assert all(p.value_kw >= 0 for p in result.points)
    assert all(not pd.isna(p.value_kw) for p in result.points)
    print("✅ 基线契约通过")

def test_contract_xgboost():
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*20)]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': [50+30*np.sin(2*np.pi*i/96) for i in range(len(timestamps))]})
    forecaster = XGBoostLoadForecaster(min_history_days=7)
    forecaster.fit(df)
    result = forecaster.predict_next_day(df, base + timedelta(days=20))
    assert len(result.points) == 96
    assert all(p.value_kw >= 0 for p in result.points)
    print("✅ XGBoost负荷契约通过")
    # PV类似
    df_pv = pd.DataFrame({'timestamp': timestamps, 'pv_kw': [max(0,100*np.sin(np.pi*(i%96)/96)) for i in range(len(timestamps))]})
    forecaster_pv = XGBoostPVForecaster(min_history_days=7)
    forecaster_pv.fit(df_pv)
    result_pv = forecaster_pv.predict_next_day(df_pv, base + timedelta(days=20))
    assert len(result_pv.points) == 96
    assert all(p.value_kw >= 0 for p in result_pv.points)
    print("✅ XGBoost光伏契约通过")

def test_contract_milp():
    optimizer = MilpBatteryOptimizer()
    request = {'load_forecast':[50]*96, 'pv_forecast':[10]*96, 'price_series':[0.5]*96, 'current_soc':50,
               'battery_capacity_kwh':200, 'soc_min':20, 'soc_max':90, 'charge_power_max':10,
               'discharge_power_max':10, 'max_import_power':300, 'allow_export':True, 'max_export_power':100}
    result = optimizer.optimize(request)
    assert result.success in [True, False]
    if result.success:
        assert len(result.schedule) == 96
        for point in result.schedule:
            assert 0 <= point.predicted_soc <= 100
    print("✅ MILP契约通过")