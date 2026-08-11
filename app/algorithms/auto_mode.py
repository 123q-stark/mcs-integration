"""
AUTO模式推荐：纯规则状态机。
"""
from .interfaces import AutoModeSelector


class AutoModeSelectorRule(AutoModeSelector):
    def select(self, context: dict) -> str:
        """
        context 应包含：
            current_soc: float
            backup_soc_target: float
            forecast_available: bool
            schedule_available: bool
            any_device_error: bool
            current_price_level: str  # 'peak'/'flat'/'valley'
            pv_power: float
            load_power: float
            可选其他
        """
        # 优先级：设备异常 -> SAFE
        if context.get('any_device_error', False):
            return 'SAFE'

        # 如果没有预测或调度可用，也建议 SAFE 或 PV_PRIORITY
        if not context.get('forecast_available', False) or not context.get('schedule_available', False):
            return 'PV_PRIORITY'

        # 如果SOC低于备用目标且当前是峰时，建议 GRID_BACKUP（充电）
        soc = context.get('current_soc', 50)
        backup = context.get('backup_soc_target', 50)
        price_level = context.get('current_price_level', 'flat')

        if soc < backup and price_level in ('peak', 'flat'):
            # 如果SOC严重低，优先充电
            if soc < backup - 10:
                return 'GRID_BACKUP'
            # 否则可以经济调度
            return 'ECONOMIC_SCHEDULE'

        # 如果有有效的调度计划，使用经济调度
        if context.get('schedule_available', False):
            return 'ECONOMIC_SCHEDULE'

        # 默认 PV_PRIORITY
        return 'PV_PRIORITY'