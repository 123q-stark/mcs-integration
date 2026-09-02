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
from app.models.device_telemetry import DeviceTelemetry


class DeviceRuntimeService:
    """设备运行时服务"""

    def __init__(
        self,
        simulator: SimulatorAdapter,
        database,  # A-锁库修复: 持有 Database，不持有 Repository/Session
    ):
        """
        初始化设备运行时服务

        Args:
            simulator: 模拟器适配器实例
            database: Database 对象
        """
        self.simulator = simulator
        self.database = database

    # ==================== A-锁库修复: 短 Session 写入 ====================

    def _save_telemetry(self, records: List[DeviceTelemetry]) -> None:
        """
        使用短生命周期 Session 保存遥测数据
        每次写入创建新的 Session，写入后自动 commit 并释放锁
        """
        from app.repositories.device_telemetry_repository import DeviceTelemetryRepository

        with self.database.session() as db:
            repo = DeviceTelemetryRepository(db)
            repo.add_many(records)
            # with 块结束自动 commit，Session 关闭，锁释放

    # ==================== P0-02: 清空遥测历史 ====================

    def _clear_telemetry(self) -> None:
        """
        P0-02: 清空所有遥测历史（Replace 模式用）
        """
        from app.repositories.device_telemetry_repository import DeviceTelemetryRepository

        with self.database.session() as db:
            repo = DeviceTelemetryRepository(db)
            repo.clear_runtime_history()

    # ==================== 批量历史生成（P0-02 Replace 模式） ====================

    def generate_history(self, days: int = 30, seed: int = 2026) -> Dict[str, Any]:
        """
        快速生成历史数据（A-11）
        P0-02: Replace 模式，每次生成前清空所有历史
        """
        start_time = time.time()

        # P0-02: 清空所有历史（Replace 模式）
        self._clear_telemetry()

        # 重置 Simulator（固定种子）
        self.simulator.reset(seed=seed)

        # P0-03: 固定仿真起始时间（与 Simulator 的 simulated_hour=6.0 对齐）
        sim_time = datetime(2026, 1, 1, 6, 0, 0)

        total_steps = days * 96
        all_records: List[DeviceTelemetry] = []

        print(f"[DeviceRuntimeService] 开始生成 {days} 天历史数据（共 {total_steps} 个时刻）...")

        for step_idx in range(total_steps):
            state = self.simulator.get_state_without_advance()
            pv_total = state.pv_power
            load_total = state.load_power
            current_soc = state.storage_soc or 50.0

            if pv_total > load_total and current_soc < 90.0:
                charge_power = min(pv_total - load_total, 10.0)
                target = -charge_power
            elif pv_total < load_total and current_soc > 20.0:
                discharge_power = min(load_total - pv_total, 10.0)
                target = discharge_power
            else:
                target = 0.0

            self.simulator.step_with_control(storage_power_target=target)

            # P0-03: 使用仿真时间戳
            sim_timestamp = sim_time
            sim_time += timedelta(minutes=15)

            devices = self.simulator.get_all_devices_state()
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
                        created_at=sim_timestamp,  # P0-03: 仿真时间
                    )
                )

            if (step_idx + 1) % 96 == 0:
                print(f"[DeviceRuntimeService] 已生成 {step_idx + 1} / {total_steps} 步 "
                      f"({(step_idx + 1) // 96} 天)")

        print(f"[DeviceRuntimeService] 正在写入 {len(all_records)} 条遥测记录...")
        self._save_telemetry(all_records)

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

    # ==================== A-P0-01: 正式只读接口 ====================

    def get_system_state(self):
        return self.simulator.get_state_without_advance()

    def get_device_status(self, device_code: str):
        all_devices = self.simulator.get_all_devices_state()
        for dev in all_devices:
            if dev.device_code == device_code:
                return dev
        return None

    # ==================== A-08: 执行 ControlDecision（P0-03 统一时间） ====================

    def execute(self, decision) -> Dict[str, Any]:
        try:
            current_state = self.simulator.get_state_without_advance()
            current_soc = current_state.storage_soc or 50.0

            target = decision.storage_power_target
            max_power = 10.0
            if hasattr(self.simulator, '_battery_rated_power_kw'):
                max_power = self.simulator._battery_rated_power_kw

            target = max(-max_power, min(max_power, target))

            if target > 0 and current_soc <= 20.0:
                target = 0.0
            if target < 0 and current_soc >= 90.0:
                target = 0.0

            self.simulator.step_with_control(storage_power_target=target)

            after_state = self.simulator.get_state_without_advance()
            actual_power = after_state.storage_power

            # P0-03: 获取仿真时间戳
            sim_timestamp = self.simulator.get_current_timestamp()

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
                        created_at=sim_timestamp,  # P0-03: 仿真时间
                    )
                )

            self._save_telemetry(records)

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

    # ==================== A-P1-07: 手动控制（A-07 修复：不推进时间） ====================

    def manual_control(self, command) -> Dict[str, Any]:
        """
        手动控制充电桩（A-07 修复版）

        文档要求：07-2 只有 run_cycle/step/generate_history 允许推进时间
        手动控制不应推进时间，只改变充电桩状态并更新 Grid 和聚合状态。

        修改说明：
        - 原实现调用 step_with_control() 会推进时间（+15分钟）
        - 现在使用 set_charger_enabled() 直接修改状态，不推进时间
        """
        try:
            device_code = command.device_code
            cmd = command.command

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

            if cmd == "start":
                enabled = True
                status_msg = f"充电桩 {device_code} 已启动"
            elif cmd == "stop":
                enabled = False
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
                status_msg = f"充电桩 {device_code} 功率上限设置为 {power_limit}kW（当前版本功率限制暂不生效）"
            else:
                return {
                    "success": False,
                    "message": f"不支持的命令: {cmd}",
                    "device_code": device_code,
                    "power_kw": 0.0,
                    "enabled": False,
                    "status": "unknown_command",
                }

            # ===== A-07 修复：直接设置充电桩状态，不推进时间 =====
            # set_charger_enabled 内部已调用 _update_grid() 和 _update_aggregate_state()
            self.simulator.set_charger_enabled(device_code, enabled)
            # ======================================================

            # 获取当前仿真时间戳（同一时刻，不推进时间）
            sim_timestamp = self.simulator.get_current_timestamp()

            # 保存遥测记录（所有 12 个设备在同一时刻的状态）
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
                        created_at=sim_timestamp,  # 同一时刻，不推进时间
                    )
                )

            self._save_telemetry(records)

            # 获取更新后的充电桩状态
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