import pytest
import pandas as pd
from datetime import datetime, timedelta
from app.algorithms.baseline_forecast import HistoricalSameSlotBaseline

def test_baseline_load():
    base = datetime(2026, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=15*i) for i in range(96*10)]
    load_data = [50 + 10*(i%24) for i in range(len(timestamps))]
    df = pd.DataFrame({'timestamp': timestamps, 'load_kw': load_data})

    forecaster = HistoricalSameSlotBaseline(n_days=7)
    result = forecaster.predict_next_day(df, base + timedelta(days=10), target='load')
    assert len(result.points) == 96
    assert all(p.value_kw >= 0 for p in result.points)
    assert result.target == 'load'
    print("基线负荷预测测试通过")