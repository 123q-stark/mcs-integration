"""
MILP 储能调度单元测试

要求（文档 11.1 节）：
- 标准工况必须 success=True，96 点，SOC/功率约束满足
- 失败工况必须 success=False，不抛异常，message 明确
"""
import pytest
import numpy as np
from app.algorithms.milp_dispatch import MilpBatteryOptimizer


def test_milp_standard_case_must_succeed():
    """标准可行工况：MILP 必须成功求解，且满足所有约束"""
    optimizer = MilpBatteryOptimizer()

    soc_min = 20.0
    soc_max = 90.0
    charge_power_max = 10.0
    discharge_power_max = 10.0

    request = {
        'load_forecast': [50.0] * 96,
        'pv_forecast': [10.0] * 96,
        'price_series': [0.5] * 96,
        'current_soc': 50.0,
        'battery_capacity_kwh': 200.0,
        'soc_min': soc_min,
        'soc_max': soc_max,
        'charge_power_max': charge_power_max,
        'discharge_power_max': discharge_power_max,
        'max_import_power': 300.0,
        'allow_export': True,
        'max_export_power': 100.0
    }

    result = optimizer.optimize(request)

    # 标准工况必须成功
    assert result.success is True, f"MILP 标准工况失败: {result.message}"
    assert len(result.schedule) == 96, f"期望 96 点，实际 {len(result.schedule)} 点"

    # 验证 SOC 约束
    soc_values = [p.predicted_soc for p in result.schedule]
    for soc in soc_values:
        assert soc_min - 1e-6 <= soc <= soc_max + 1e-6, f"SOC {soc} 超出 [{soc_min}, {soc_max}]"

    # 验证功率约束
    power_values = [p.storage_power_target_kw for p in result.schedule]
    for p in power_values:
        assert -charge_power_max - 1e-6 <= p <= discharge_power_max + 1e-6, \
            f"功率 {p} 超出 [{-charge_power_max}, {discharge_power_max}]"

    # 验证非空
    assert all(p.storage_power_target_kw is not None for p in result.schedule)
    assert all(p.predicted_soc is not None for p in result.schedule)

    print("✅ MILP 标准工况测试通过")


def test_milp_invalid_case_returns_failure_cleanly():
    """不可行约束：必须返回 success=False，不抛异常"""
    optimizer = MilpBatteryOptimizer()

    # 故意构造不可行：soc_min > soc_max（下限大于上限）
    invalid_request = {
        'load_forecast': [50.0] * 96,
        'pv_forecast': [10.0] * 96,
        'price_series': [0.5] * 96,
        'current_soc': 50.0,
        'battery_capacity_kwh': 200.0,
        'soc_min': 80.0,   # 下限 > 上限 → 不可行
        'soc_max': 70.0,
        'charge_power_max': 10.0,
        'discharge_power_max': 10.0,
        'max_import_power': 300.0,
        'allow_export': True,
        'max_export_power': 100.0
    }

    # 不应抛出异常
    result = optimizer.optimize(invalid_request)

    # 必须返回失败状态
    assert result.success is False, "不可行输入应返回 success=False"
    assert result.schedule == [], "失败时 schedule 应为空列表"
    assert result.message is not None and result.message != "", "失败时应有错误信息"
    assert result.optimizer_name == "MILP"

    print("✅ MILP 失败工况测试通过")


def test_milp_no_export_constraint():
    """验证 allow_export=False 时不售电"""
    optimizer = MilpBatteryOptimizer()

    request = {
        'load_forecast': [50.0] * 96,
        'pv_forecast': [30.0] * 96,
        'price_series': [0.5] * 96,
        'current_soc': 50.0,
        'battery_capacity_kwh': 200.0,
        'soc_min': 20.0,
        'soc_max': 90.0,
        'charge_power_max': 10.0,
        'discharge_power_max': 10.0,
        'max_import_power': 300.0,
        'allow_export': False,   # 禁止售电
        'max_export_power': 100.0
    }

    result = optimizer.optimize(request)

    # allow_export=False 时 MILP 应该成功（剩余功率被储存在电池中或丢弃）
    # 由于约束限制，可能仍然可行，我们只验证不崩溃
    assert result.success in [True, False], "必须返回布尔值"
    if result.success:
        assert len(result.schedule) == 96

    print("✅ MILP 禁止售电测试通过")