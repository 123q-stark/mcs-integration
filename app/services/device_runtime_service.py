"""
设备运行时服务
负责设备 Simulator 的执行编排，包括：
- 批量历史生成（A-11）
- 执行 B 的 ControlDecision（A-8）
"""
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.devices.simulator import SimulatorAdapter
from app.repositories.device_telemetry_repository import DeviceTelemetryRepository
from app.repositories.strategy_repository import StrategyRepository
from app.models.device_telemetry import DeviceTelemetry
from app.schemas.common import ControlDecision, ControlExecutionResult


class DeviceRuntimeService:
    """设备运行时服务"""

    def __init__(
        self,
        simulator: SimulatorAdapter,
        telemetry_repo: DeviceTelemetryRepository,
        strategy_repo: StrategyRepository,  # ← A-8 新增
    ):
        """
        初始化设备运行时服务

        Args:
            simulator: 模拟器适配器实例
            telemetry_repo: 设备遥测数据访问层
            strategy_repo: 策略配置数据访问层（A-8 新增）
        """
        self.simulator = simulator
        self.telemetry_repo = telemetry_repo
        self.strategy_repo = strategy_repo

    def generate_history(self, days: int = 30, seed: int = 2026) -> Dict[str, Any]:
        """
        快速生成历史数据（A-11）

        生成指定天数的历史遥测数据，每个时刻包含 12 个逻辑设备的状态。
        使用固定随机种子确保可复现。

        Args:
            days: 生成天数（默认 30，最大 365）
            seed: 随机种子（默认 2026）

        Returns:
            dict: {
                "success": bool,
                "total_steps": int,
                "total_records": int,
                "message": str
            }
        """
        start_time = time.time()

        # 1. 重置 Simulator（固定种子）
        self.simulator.reset(seed=seed)

        # 2. 清空现有遥测历史（避免重复）
        self.telemetry_repo.clear_runtime_history()

        total_steps = days * 96
        all_records: List[DeviceTelemetry] = []

        print(f"[DeviceRuntimeService] 开始生成 {days} 天历史数据（共 {total_steps} 个时刻）...")

        # 3. 生成历史
        for step_idx in range(total_steps):
            # 获取当前状态（不推进时间）
            state = self.simulator.get_state_without_advance()

            pv_total = state.pv_power
            load_total = state.load_power
            current_soc = state.storage_soc or 50.0

            # 使用 PV_PRIORITY 简化版决定储能功率
            if pv_total > load_total and current_soc < 90.0:
                charge_power = min(pv_total - load_total, 10.0)
                target = -charge_power
            elif pv_total < load_total and current_soc > 20.0:
                discharge_power = min(load_total - pv_total, 10.0)
                target = discharge_power
            else:
                target = 0.0

            # 推进一步（应用控制）
            self.simulator.step_with_control(storage_power_target=target)

            # 获取当前所有设备状态
            devices = self.simulator.get_all_devices_state()

            # 收集遥测记录
            for dev in devices:
                all_records.append(
                    DeviceTelemetry(
                        device_code=dev.device_code,
                        device_type=dev.device_type,
                        power_kw=dev.power_kw,
                        voltage_v=dev.voltage_v,
                        current_a=dev.current_a,
                        temperature_c=dev.temperature_c,
                        energy_kwh=dev.energy_kwh,
                        soc=dev.soc,
                        soh=dev.soh,
                        enabled=dev.enabled,
                        status=dev.status,
                        quality=dev.quality or "good",
                    )
                )

            # 每 96 步（一天）打印进度
            if (step_idx + 1) % 96 == 0:
                print(f"[DeviceRuntimeService] 已生成 {step_idx + 1} / {total_steps} 步 "
                      f"({(step_idx + 1) // 96} 天)")

        # 4. 批量写入数据库
        print(f"[DeviceRuntimeService] 正在写入 {len(all_records)} 条遥测记录...")
        self.telemetry_repo.add_many(all_records)

        elapsed = time.time() - start_time

        message = (
            f"成功生成 {days} 天历史（{total_steps} 个时刻，"
            f"{len(all_records)} 条遥测记录），耗时 {elapsed:.2f} 秒"
        )
        print(f"[DeviceRuntimeService] ✅ {message}")

        return {
            "success": True,
            "total_steps": total_steps,
            "total_records": len(all_records),
            "message": message,
        }

    # ==================== A-08: 执行 ControlDecision ====================

    def execute(self, decision: ControlDecision) -> ControlExecutionResult:
        """
        执行 B 下发的控制决策（A-8）

        职责：
        1. 读取策略约束（SOC 上下限、功率上下限）
        2. 对储能功率做安全限幅
        3. 处理充电桩控制（若 decision.charger_targets 非空）
        4. 调用 Simulator 执行
        5. 返回执行结果

        Args:
            decision: B 下发的控制决策

        Returns:
            ControlExecutionResult: 执行结果
        """
        try:
            # 1. 读取当前策略约束
            config = self.strategy_repo.get_active_config()
            if config is None:
                return ControlExecutionResult(
                    decision_id=decision.decision_id if hasattr(decision, 'decision_id') else None,
                    success=False,
                    storage_power_actual_kw=0.0,
                    charger_results=[],
                    message="未找到激活的策略配置",
                    executed_at=datetime.utcnow(),
                )

            soc_min = config.soc_min
            soc_max = config.soc_max
            max_charge = config.charge_power_kw
            max_discharge = config.discharge_power_kw

            # 2. 获取当前状态（用于 SOC 边界判断）
            current_state = self.simulator.get_state_without_advance()
            current_soc = current_state.storage_soc or 50.0

            # 3. 安全限幅：储能功率
            target = decision.storage_power_target

            # 3a. 功率边界限幅
            if target > 0:  # 放电
                target = min(target, max_discharge)
                # SOC 下限限幅
                if current_soc <= soc_min:
                    target = 0.0
            elif target < 0:  # 充电
                target = max(target, -max_charge)
                # SOC 上限限幅
                if current_soc >= soc_max:
                    target = 0.0
            else:
                target = 0.0

            # 4. 构建 charger_targets（包含 power_limit_kw）
            charger_mods = []
            if hasattr(decision, 'charger_targets') and decision.charger_targets:
                for ct in decision.charger_targets:
                    mod = {"device_code": ct.device_code}
                    if ct.enabled is not None:
                        mod["enabled"] = ct.enabled
                    if ct.power_limit_kw is not None:
                        mod["power_limit_kw"] = ct.power_limit_kw
                    charger_mods.append(mod)

            # 5. 调用 Simulator 执行
            self.simulator.step_with_control(
                storage_power_target=target,
                charger_targets=charger_mods if charger_mods else None,
            )

            # 6. 获取执行后状态
            after_state = self.simulator.get_state_without_advance()
            actual_power = after_state.storage_power

            # 7. 保存遥测
            devices = self.simulator.get_all_devices_state()
            records = []
            for dev in devices:
                records.append(
                    DeviceTelemetry(
                        device_code=dev.device_code,
                        device_type=dev.device_type,
                        power_kw=dev.power_kw,
                        voltage_v=dev.voltage_v,
                        current_a=dev.current_a,
                        temperature_c=dev.temperature_c,
                        energy_kwh=dev.energy_kwh,
                        soc=dev.soc,
                        soh=dev.soh,
                        enabled=dev.enabled,
                        status=dev.status,
                        quality=dev.quality or "good",
                    )
                )
            self.telemetry_repo.add_many(records)

            # 8. 返回执行结果
            charger_results = []
            if hasattr(decision, 'charger_targets') and decision.charger_targets:
                charger_results = [
                    {"device_code": ct.device_code, "applied": True}
                    for ct in decision.charger_targets
                ]

            return ControlExecutionResult(
                decision_id=decision.decision_id if hasattr(decision, 'decision_id') else None,
                success=True,
                storage_power_actual_kw=actual_power,
                charger_results=charger_results,
                message=f"执行成功，储能功率={actual_power:.2f}kW",
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            return ControlExecutionResult(
                decision_id=decision.decision_id if hasattr(decision, 'decision_id') else None,
                success=False,
                storage_power_actual_kw=0.0,
                charger_results=[],
                message=f"执行失败: {str(e)}",
                executed_at=datetime.utcnow(),
            )