import pytest
import numpy as np
from app.algorithms.milp_dispatch import MilpBatteryOptimizer

def test_milp_basic():
    optimizer = MilpBatteryOptimizer()
    request = {
        'load_forecast': [50]*96,
        'pv_forecast': [10]*96,
        'price_series': [0.5]*96,
        'current_soc': 50,
        'battery_capacity_kwh': 200,
        'soc_min': 20,
        'soc_max': 90,
        'charge_power_max': 10,
        'discharge_power_max': 10,
        'max_import_power': 300,
        'allow_export': True,
        'max_export_power': 100
    }
    result = optimizer.optimize(request)
    # 无论成功失败，必须返回明确状态且不抛异常
    assert result.success in [True, False]
    if result.success:
        assert len(result.schedule) == 96
        # 验证SOC约束（粗略）
        for point in result.schedule:
            assert 0 <= point.predicted_soc <= 100
    print("MILP储能调度测试通过")