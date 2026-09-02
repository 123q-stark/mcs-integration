import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.algorithms.xgboost_forecast import XGBoostLoadForecaster, XGBoostPVForecaster


# ============ 原有测试 ============

def test_xgboost_load():
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*10)]
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
    pv_data = [max(0, 100*np.sin(np.pi*(i%96)/96)) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'pv_kw': pv_data})

    forecaster = XGBoostPVForecaster(min_history_days=7)
    forecaster.fit(df)
    result = forecaster.predict_next_day(df, base + timedelta(days=10))
    assert len(result.points) == 96
    assert all(p.value_kw >= 0 for p in result.points)
    print("XGBoost光伏预测测试通过")


# ============ P0-04: Rolling 特征泄漏测试（使用 100+ 行数据确保 lag_96 有效） ============

def test_rolling_features_no_leak():
    """P0-04: 验证 rolling 特征不包含当前目标值"""
    from app.algorithms.features import build_load_features

    # 需要至少 100 行数据，让 lag_96 不产生 NaN
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(105)]
    # 前 96 个值为 1~96，第 97 个值为 1000（作为异常值测试），后续为正常值
    load_values = [float(i+1) for i in range(96)] + [1000.0] + [float(i+1) for i in range(8)]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': load_values})

    df_features = build_load_features(df)

    # 找到 load_kw == 1000 的行
    mask = np.isclose(df_features['load_kw'].values, 1000.0, rtol=1e-6)
    row = df_features[mask].iloc[0]

    rolling_mean_4 = row['rolling_mean_4']
    # rolling_mean_4 应该由前 4 个值（96, 95, 94, 93）计算，不包含 1000
    # 注意索引：第 97 个值（索引 96）的 rolling_mean_4 使用 shift(1) 后由索引 95,94,93,92 计算
    expected = (96.0 + 95.0 + 94.0 + 93.0) / 4
    assert abs(rolling_mean_4 - expected) < 0.001, \
        f"rolling_mean_4 应为 {expected}，实际为 {rolling_mean_4}"

    # 验证 lag_1 是前一个值（96.0），不是当前值（1000）
    lag_1 = row['lag_1']
    assert abs(lag_1 - 96.0) < 0.001, f"lag_1 应为 96.0，实际为 {lag_1}"


def test_rolling_features_pv_no_leak():
    """P0-04: 验证 PV rolling 特征不包含当前目标值"""
    from app.algorithms.features import build_pv_features

    # 需要至少 100 行数据，让 lag_96 不产生 NaN
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(105)]
    pv_values = [float(i+1) for i in range(96)] + [1000.0] + [float(i+1) for i in range(8)]
    df = pd.DataFrame({'timestamp': timestamps, 'pv_kw': pv_values})

    df_features = build_pv_features(df)

    mask = np.isclose(df_features['pv_kw'].values, 1000.0, rtol=1e-6)
    row = df_features[mask].iloc[0]
    rolling_mean_96 = row['rolling_mean_96']

    # rolling_mean_96 由前 96 个值（1~96）计算，不包含 1000
    expected = sum(range(1, 97)) / 96
    assert abs(rolling_mean_96 - expected) < 0.001, \
        f"rolling_mean_96 应为 {expected}，实际为 {rolling_mean_96}"


# ============ P1-06: MAE/RMSE 非空测试 ============

def test_xgboost_load_mae_rmse_not_none():
    """P1-06: 验证 XGBoost 训练后 MAE/RMSE 不为 None"""
    np.random.seed(2026)
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*20)]
    load_data = [50 + 30*np.sin(2*np.pi*i/96) + np.random.normal(0, 2) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': load_data})

    forecaster = XGBoostLoadForecaster(min_history_days=7)
    forecaster.fit(df)
    result = forecaster.predict_next_day(df, base + timedelta(days=20))

    assert result.mae is not None, "MAE 不应为 None"
    assert result.rmse is not None, "RMSE 不应为 None"
    assert result.mae >= 0, "MAE 应 >= 0"
    assert result.rmse >= 0, "RMSE 应 >= 0"
    print(f"负荷预测 MAE={result.mae:.2f}, RMSE={result.rmse:.2f}")


def test_xgboost_pv_mae_rmse_not_none():
    """P1-06: 验证 PV XGBoost 训练后 MAE/RMSE 不为 None"""
    np.random.seed(2026)
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*20)]
    pv_data = [max(0, 80*np.sin(np.pi*(i%96)/96) + np.random.normal(0, 3)) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'pv_kw': pv_data})

    forecaster = XGBoostPVForecaster(min_history_days=7)
    forecaster.fit(df)
    result = forecaster.predict_next_day(df, base + timedelta(days=20))

    assert result.mae is not None, "PV MAE 不应为 None"
    assert result.rmse is not None, "PV RMSE 不应为 None"
    assert result.mae >= 0, "PV MAE 应 >= 0"
    assert result.rmse >= 0, "PV RMSE 应 >= 0"
    print(f"PV 预测 MAE={result.mae:.2f}, RMSE={result.rmse:.2f}")


# ============ P1-07: 元数据完整性测试 ============

def test_model_store_metadata_complete():
    """P1-07: 验证保存的模型元数据完整"""
    from app.algorithms.model_store import ModelStore

    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*20)]
    load_data = [50 + 30*np.sin(2*np.pi*i/96) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': load_data})

    forecaster = XGBoostLoadForecaster(min_history_days=7)
    forecaster.fit(df)

    store = ModelStore()
    meta = store.load_meta("xgboost_load")

    assert meta is not None, "元数据不存在"
    assert 'feature_version' in meta, "缺少 feature_version"
    assert meta['feature_version'] == 'v1.7', "feature_version 应为 v1.7"
    assert 'metrics' in meta, "缺少 metrics"
    assert 'mae' in meta['metrics'], "metrics 中缺少 mae"
    assert 'rmse' in meta['metrics'], "metrics 中缺少 rmse"
    assert meta['metrics']['mae'] >= 0, "MAE 应 >= 0"
    assert meta['metrics']['rmse'] >= 0, "RMSE 应 >= 0"
    print("元数据完整性验证通过")


def test_model_store_metadata_complete_pv():
    """P1-07: 验证 PV 模型元数据完整"""
    from app.algorithms.model_store import ModelStore

    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*20)]
    pv_data = [max(0, 100*np.sin(np.pi*(i%96)/96)) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'pv_kw': pv_data})

    forecaster = XGBoostPVForecaster(min_history_days=7)
    forecaster.fit(df)

    store = ModelStore()
    meta = store.load_meta("xgboost_pv")

    assert meta is not None, "PV 元数据不存在"
    assert 'feature_version' in meta, "PV 缺少 feature_version"
    assert meta['feature_version'] == 'v1.7', "PV feature_version 应为 v1.7"
    assert 'metrics' in meta, "PV 缺少 metrics"
    assert 'mae' in meta['metrics'], "PV metrics 中缺少 mae"
    assert 'rmse' in meta['metrics'], "PV metrics 中缺少 rmse"
    assert meta['metrics']['mae'] >= 0, "PV MAE 应 >= 0"
    assert meta['metrics']['rmse'] >= 0, "PV RMSE 应 >= 0"
    print("PV 元数据完整性验证通过")