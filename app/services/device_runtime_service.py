"""
设备运行时服务
负责设备 Simulator 的执行编排，包括：
- 批量历史生成（A-11）
- 执行 B 的 ControlDecision（A-8，后续实现）
"""
import time
from typing import Optional, List, Dict, Any

from app.devices.simulator import SimulatorAdapter
from app.repositories.device_telemetry_repository import DeviceTelemetryRepository
from app.models.device_telemetry import DeviceTelemetry


class DeviceRuntimeService:
    """设备运行时服务"""

    def __init__(
        self,
        simulator: SimulatorAdapter,
        telemetry_repo: DeviceTelemetryRepository,
    ):
        """
        初始化设备运行时服务

        Args:
            simulator: 模拟器适配器实例
            telemetry_repo: 设备遥测数据访问层
        """
        self.simulator = simulator
        self.telemetry_repo = telemetry_repo

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
        records_per_step = 12  # 12 个逻辑设备
        all_records: List[DeviceTelemetry] = []

        # 3. 生成历史
        for step_idx in range(total_steps):
            # 获取当前状态（不推进时间）
            state = self.simulator.get_state_without_advance()

            pv_total = state.pv_power
            load_total = state.load_power
            current_soc = state.storage_soc or 50.0

            # 使用 PV_PRIORITY 简化版决定储能功率
            # - PV > load 且 SOC < 90% → 充电（负功率）
            # - PV < load 且 SOC > 20% → 放电（正功率）
            # - 否则 idle
            if pv_total > load_total and current_soc < 90.0:
                # 充电功率不超过 PV 富余量，且不超过 10kW
                charge_power = min(pv_total - load_total, 10.0)
                target = -charge_power
            elif pv_total < load_total and current_soc > 20.0:
                # 放电功率不超过负荷缺口，且不超过 10kW
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

        # 4. 批量写入数据库（一次性提交，提升性能）
        self.telemetry_repo.add_many(all_records)

        elapsed = time.time() - start_time

        message = (
            f"成功生成 {days} 天历史（{total_steps} 个时刻，"
            f"{len(all_records)} 条遥测记录），耗时 {elapsed:.2f} 秒"
        )

        return {
            "success": True,
            "total_steps": total_steps,
            "total_records": len(all_records),
            "message": message,
        }