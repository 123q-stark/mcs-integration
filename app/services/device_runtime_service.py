"""
设备运行时服务
负责设备 Simulator 的执行编排，包括：
- 批量历史生成（A-11）
- 执行 B 的 ControlDecision（A-8）
- 手动控制设备（A-P1-07）
"""
import time
from datetime import datetime, timedelta
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

        # A-P0-03: 固定仿真起始时间（与 Simulator 的 simulated_hour=6.0 对齐）
        sim_time = datetime(2026, 1, 1, 6, 0, 0)

        # 2. 清空现有遥测历史（避免重复）
        self.telemetry_repo.clear_runtime_history()

        total_steps = days * 96
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

            # A-P0-03: 使用手动维护的仿真时间戳
            sim_timestamp = sim_time
            sim_time += timedelta(minutes=15)

            # 获取当前所有设备状态
            devices = self.simulator.get_all_devices_state()

            # 收集遥测记录（显式传入 created_at）
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
                        created_at=sim_timestamp,
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

    # ==================== A-P0-01: 正式只读接口 ====================

    def get_system_state(self):
        """
        获取当前系统状态（纯只读，不推进时间）
        作为 DeviceReadPort 的正式接口
        """
        return self.simulator.get_state_without_advance()

    def get_device_status(self, device_code: str):
        """
        获取单个设备状态（纯只读）
        """
        all_devices = self.simulator.get_all_devices_state()
        for dev in all_devices:
            if dev.device_code == device_code:
                return dev
        return None

    # ==================== A-08: 执行 ControlDecision ====================

    def execute(self, decision) -> Dict[str, Any]:
        """
        执行 B 下发的控制决策（A-8）
        执行后自动保存遥测历史

        Args:
            decision: ControlDecision 对象

        Returns:
            dict: {
                "success": bool,
                "storage_power_actual_kw": float,
                "message": str
            }
        """
        try:
            # 1. 获取当前状态
            current_state = self.simulator.get_state_without_advance()
            current_soc = current_state.storage_soc or 50.0

            # 2. A-P1-02: 使用 Simulator 中的 Battery 额定功率进行限幅
            target = decision.storage_power_target

            # 从 Simulator 获取 Battery 额定功率（如果存在）
            max_power = 10.0  # 默认值
            if hasattr(self.simulator, '_battery_rated_power_kw'):
                max_power = self.simulator._battery_rated_power_kw

            # 功率限幅
            target = max(-max_power, min(max_power, target))

            # SOC 边界限幅
            if target > 0 and current_soc <= 20.0:  # 放电时 SOC 过低则停止
                target = 0.0
            if target < 0 and current_soc >= 90.0:  # 充电时 SOC 过高则停止
                target = 0.0

            # 3. 调用 Simulator 执行
            self.simulator.step_with_control(storage_power_target=target)

            # 4. 获取执行后状态
            after_state = self.simulator.get_state_without_advance()
            actual_power = after_state.storage_power

            # 5. 保存遥测历史（A-P0-02: 由 DeviceRuntimeService 统一保存）
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

            # 6. 返回执行结果
            return {
                "success": True,
                "storage_power_actual_kw": actual_power,
                "message": f"执行成功，储能功率={actual_power:.2f}kW",
            }

        except Exception as e:
            return {
                "success": False,
                "storage_power_actual_kw": 0.0,
                "message": f"执行失败: {str(e)}",
            }

    # ==================== A-P1-07: 手动控制 ====================

    def manual_control(self, command) -> Dict[str, Any]:
        """
        手动控制设备（A-P1-07）
        走正式 DeviceExecutionPort，执行后自动保存遥测历史

        Args:
            command: ManualDeviceControl 对象

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "device_code": str,
                "power_kw": float,
                "enabled": bool,
                "status": str
            }
        """
        try:
            device_code = command.device_code
            cmd = command.command

            # 1. 查找目标充电桩
            target_charger = None
            for charger in self.simulator.get_chargers():
                if charger.device_code == device_code:
                    target_charger = charger
                    break

            if target_charger is None:
                return {
                    "success": False,
                    "message": f"设备 {device_code} 未找到或不是充电桩",
                    "device_code": device_code,
                    "power_kw": 0.0,
                    "enabled": False,
                    "status": "not_found",
                }

            # 2. 构造 charger_targets
            if cmd == "start":
                enabled = True
                power_limit = None
                status_msg = f"充电桩 {device_code} 已启动"
            elif cmd == "stop":
                enabled = False
                power_limit = None
                status_msg = f"充电桩 {device_code} 已停止"
            elif cmd == "set_power":
                enabled = True
                power_limit = command.target_power_kw
                if power_limit is None or power_limit <= 0:
                    return {
                        "success": False,
                        "message": "set_power 需要有效的 target_power_kw",
                        "device_code": device_code,
                        "power_kw": 0.0,
                        "enabled": False,
                        "status": "invalid_power",
                    }
                status_msg = f"充电桩 {device_code} 功率上限设置为 {power_limit}kW"
            else:
                return {
                    "success": False,
                    "message": f"不支持的命令: {cmd}",
                    "device_code": device_code,
                    "power_kw": 0.0,
                    "enabled": False,
                    "status": "unknown_command",
                }

            # 3. 执行控制
            charger_mods = [{
                "device_code": device_code,
                "enabled": enabled,
                "power_limit_kw": power_limit,
            }]
            self.simulator.step_with_control(
                storage_power_target=0.0,
                charger_targets=charger_mods,
            )

            # 4. 保存遥测历史
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
            self.telemetry_repo.db.commit()
            # 5. 返回结果
            after_charger = None
            for charger in self.simulator.get_chargers():
                if charger.device_code == device_code:
                    after_charger = charger
                    break

            return {
                "success": True,
                "message": status_msg,
                "device_code": device_code,
                "power_kw": after_charger.power_kw if after_charger else 0.0,
                "enabled": after_charger.enabled if after_charger else False,
                "status": after_charger.status if after_charger else "unknown",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"控制失败: {str(e)}",
                "device_code": command.device_code if hasattr(command, 'device_code') else "",
                "power_kw": 0.0,
                "enabled": False,
                "status": "error",
            }