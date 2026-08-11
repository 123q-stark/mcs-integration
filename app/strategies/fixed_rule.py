from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.schemas import ControlDecision, SystemState
from app.strategies.base import EnergyStrategy


class FixedRuleStrategy(EnergyStrategy):
    """
    教学用固定规则（可配置版本）。

    策略故意写得简单，但通过统一接口与其他模块解耦。
    支持从外部传入 StrategyConfig 配置，实现参数化。
    后续可直接替换为参数化规则、预测模型或优化算法。
    """

    # 默认值（当未传入 config 时使用）
    _DEFAULT_SOC_MIN = 20.0
    _DEFAULT_SOC_MAX = 90.0
    _DEFAULT_CHARGE_POWER_KW = 10.0
    _DEFAULT_DISCHARGE_POWER_KW = 10.0

    def calculate(
        self,
        state: SystemState,
        config: Optional["StrategyConfig"] = None,
    ) -> ControlDecision:
        """
        根据系统状态和策略配置生成控制决策

        Args:
            state: 系统状态（光伏功率、负载功率、储能功率、储能 SOC）
            config: 策略配置（SOC 上下限、充放电功率），可选

        Returns:
            ControlDecision: 控制决策
        """
        # 1. 提取配置参数（优先使用传入的 config，否则使用默认值）
        if config is None:
            soc_min = self._DEFAULT_SOC_MIN
            soc_max = self._DEFAULT_SOC_MAX
            charge_power_kw = self._DEFAULT_CHARGE_POWER_KW
            discharge_power_kw = self._DEFAULT_DISCHARGE_POWER_KW
        else:
            soc_min = config.soc_min
            soc_max = config.soc_max
            charge_power_kw = config.charge_power_kw
            discharge_power_kw = config.discharge_power_kw

        pv_power = state.pv_power
        load_power = state.load_power
        storage_soc = state.storage_soc

        # 2. 计算功率差额（正=光伏有余，负=光伏不足）
        power_balance = pv_power - load_power

        # 3. 决策逻辑
        if power_balance > 0 and storage_soc < soc_max:
            # 光伏有余 + SOC 未满 → 充电
            target_power = -charge_power_kw  # 充电为负值
            action = "charge"
            message = (
                f"光伏功率 ({pv_power:.1f}kW) 高于负载 ({load_power:.1f}kW)，"
                f"且 SOC ({storage_soc:.1f}%) < {soc_max:.0f}%，"
                f"储能执行 {charge_power_kw:.1f}kW 充电。"
            )

        elif power_balance < 0 and storage_soc > soc_min:
            # 光伏不足 + SOC 高于下限 → 放电
            target_power = discharge_power_kw  # 放电为正值
            action = "discharge"
            message = (
                f"光伏功率 ({pv_power:.1f}kW) 低于负载 ({load_power:.1f}kW)，"
                f"且 SOC ({storage_soc:.1f}%) > {soc_min:.0f}%，"
                f"储能执行 {discharge_power_kw:.1f}kW 放电。"
            )

        else:
            # 其他情况 → 待机
            target_power = 0.0
            action = "idle"

            if power_balance > 0 and storage_soc >= soc_max:
                message = (
                    f"SOC ({storage_soc:.1f}%) 已达到上限 {soc_max:.0f}%，"
                    f"停止充电，储能待机。"
                )
            elif power_balance < 0 and storage_soc <= soc_min:
                message = (
                    f"SOC ({storage_soc:.1f}%) 已达到下限 {soc_min:.0f}%，"
                    f"停止放电，储能待机。"
                )
            else:
                message = "光伏与负载基本平衡，储能待机。"

        # 4. 返回控制决策
        return ControlDecision(
            storage_power_target=target_power,
            action=action,
            message=message,
            created_at=datetime.now(),
        )