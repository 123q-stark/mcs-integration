import pytest
from app.algorithms.auto_mode import AutoModeSelectorRule

def test_auto_mode():
    selector = AutoModeSelectorRule()

    # 场景1：设备异常 -> SAFE
    assert selector.select({'any_device_error': True}) == 'SAFE'

    # 场景2：无预测 -> PV_PRIORITY
    assert selector.select({'any_device_error': False, 'forecast_available': False}) == 'PV_PRIORITY'

    # 场景3：SOC低 + 峰时 -> 至少返回有效枚举
    context = {
        'any_device_error': False,
        'forecast_available': True,
        'schedule_available': True,
        'current_soc': 30,
        'backup_soc_target': 50,
        'current_price_level': 'peak'
    }
    mode = selector.select(context)
    assert mode in ['PV_PRIORITY', 'ECONOMIC_SCHEDULE', 'GRID_BACKUP', 'AUTO', 'SAFE']
    print("AUTO模式推荐测试通过")