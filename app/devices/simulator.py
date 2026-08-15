from __future__ import annotations

import math
import random
import threading
from datetime import datetime
from typing import List, Optional

from app.devices.base import DeviceAdapter
from app.schemas import ControlDecision, SystemState
from app.schemas.device_runtime import DeviceRuntimeState


class SimulatorAdapter(DeviceAdapter):
    """完整站点模拟器：5 PV + 5 Charger + Battery + Grid"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._random = random.Random(2026)

        # 固定参数
        self._simulation_step_hours = 0.25

        # ===== 5 路 PV =====
        self._pv_units: List[DeviceRuntimeState] = []
        self._init_pv_units()

        # ===== 5 个充电桩 =====
        self._chargers: List[DeviceRuntimeState] = []
        self._init_chargers()

        # ===== Battery =====
        self._battery: DeviceRuntimeState = self._init_battery()

        # ===== Grid =====
        self._grid: DeviceRuntimeState = self._init_grid()

        # ===== 当前模拟时间 =====
        self._simulated_hour = 6.0
        self._timestamp = datetime.now()

        # ===== 更新状态 =====
        self._update_aggregate_state()

        print(f"[Simulator] 初始化完成，ID: {id(self)}")

    def _init_pv_units(self) -> None:
        """初始化 5 路 PV"""
        pv_factors = [1.00, 0.95, 1.03, 0.98, 1.01]
        self._pv_units = []
        for i, factor in enumerate(pv_factors, 1):
            self._pv_units.append(
                DeviceRuntimeState(
                    device_code=f"PV00{i}",
                    device_type="pv",
                    timestamp=datetime.now(),
                    is_online=True,
                    quality="good",
                    power_kw=0.0,
                    voltage_v=220.0 + self._random.uniform(-5, 5),
                    current_a=0.0,
                    temperature_c=25.0 + self._random.uniform(-3, 3),
                    energy_kwh=0.0,
                )
            )

    def _init_chargers(self) -> None:
        """初始化 5 个充电桩"""
        self._chargers = []
        for i in range(1, 6):
            self._chargers.append(
                DeviceRuntimeState(
                    device_code=f"CHG00{i}",
                    device_type="charger",
                    timestamp=datetime.now(),
                    is_online=True,
                    quality="good",
                    power_kw=0.0,
                    voltage_v=220.0,
                    current_a=0.0,
                    energy_kwh=0.0,
                    enabled=True,
                    status="idle",
                    connected=False,
                )
            )

    def _init_battery(self) -> DeviceRuntimeState:
        """初始化 Battery"""
        return DeviceRuntimeState(
            device_code="BATT001",
            device_type="battery",
            timestamp=datetime.now(),
            is_online=True,
            quality="good",
            power_kw=0.0,
            voltage_v=400.0,
            current_a=0.0,
            temperature_c=25.0,
            energy_kwh=200.0,
            soc=50.0,
            soh=98.0,
            alarm=False,
        )

    def _init_grid(self) -> DeviceRuntimeState:
        """初始化 Grid"""
        return DeviceRuntimeState(
            device_code="GRID001",
            device_type="grid",
            timestamp=datetime.now(),
            is_online=True,
            quality="good",
            power_kw=0.0,
            voltage_v=220.0,
            current_a=0.0,
            energy_kwh=0.0,
        )

    def _update_pv_units(self, base_pv: float) -> None:
        """更新 5 路 PV 功率"""
        pv_factors = [1.00, 0.95, 1.03, 0.98, 1.01]
        total_factor = sum(pv_factors)

        for i, pv in enumerate(self._pv_units):
            # 按权重分配总 PV 功率
            pv.power_kw = round(base_pv * pv_factors[i] / total_factor, 2)
            # 加入小扰动（±2%）
            pv.power_kw = round(pv.power_kw * (1 + self._random.uniform(-0.02, 0.02)), 2)
            pv.power_kw = max(0.0, pv.power_kw)
            # 电流 = 功率 / 电压（简化）
            if pv.voltage_v and pv.voltage_v > 0:
                pv.current_a = round(pv.power_kw / pv.voltage_v * 1000, 2)

            # A-P1-01: 累加累计发电量
            # E_{k+1} = E_k + |P_k| * Δt
            energy_delta = abs(pv.power_kw) * self._simulation_step_hours
            pv.energy_kwh = round((pv.energy_kwh or 0.0) + energy_delta, 2)

            pv.timestamp = self._timestamp
            pv.is_online = True

    def _update_chargers(self, base_load: float) -> None:
        """更新 5 个充电桩功率"""
        charger_factors = [0.18, 0.22, 0.20, 0.17, 0.23]
        total_factor = sum(charger_factors)

        for i, charger in enumerate(self._chargers):
            if not charger.enabled:
                charger.power_kw = 0.0
                charger.status = "disabled"
                charger.current_a = 0.0
                charger.connected = False
                charger.timestamp = self._timestamp
                continue

            # 按权重分配总负荷
            power = base_load * charger_factors[i] / total_factor
            # 加入小扰动
            power = power * (1 + self._random.uniform(-0.05, 0.05))
            charger.power_kw = round(max(0.0, power), 2)

            if charger.power_kw > 0.5:
                charger.status = "charging"
                charger.connected = True
            else:
                charger.status = "idle"
                charger.connected = False

            if charger.voltage_v and charger.voltage_v > 0:
                charger.current_a = round(charger.power_kw / charger.voltage_v * 1000, 2)

            # A-P1-01: 累加累计用电量
            # E_{k+1} = E_k + |P_k| * Δt
            energy_delta = abs(charger.power_kw) * self._simulation_step_hours
            charger.energy_kwh = round((charger.energy_kwh or 0.0) + energy_delta, 2)

            charger.timestamp = self._timestamp
            charger.is_online = True

    def _update_battery(self, power_kw: float) -> None:
        """更新 Battery 状态"""
        self._battery.power_kw = round(power_kw, 2)
        self._battery.timestamp = self._timestamp
        self._battery.is_online = True

    def _update_grid(self) -> None:
        """更新 Grid（由功率平衡计算）"""
        pv_total = sum(pv.power_kw for pv in self._pv_units)
        load_total = sum(c.power_kw for c in self._chargers)
        battery_power = self._battery.power_kw

        grid_power = load_total - pv_total - battery_power
        self._grid.power_kw = round(grid_power, 2)

        # A-P1-01: 累加累计电网交换电量（绝对值）
        energy_delta = abs(self._grid.power_kw) * self._simulation_step_hours
        self._grid.energy_kwh = round((self._grid.energy_kwh or 0.0) + energy_delta, 2)

        self._grid.timestamp = self._timestamp
        self._grid.is_online = True

        if self._grid.voltage_v and self._grid.voltage_v > 0:
            self._grid.current_a = round(abs(self._grid.power_kw) / self._grid.voltage_v * 1000, 2)

    def _update_aggregate_state(self) -> None:
        """更新聚合 SystemState（包含扩展字段）"""
        pv_total = sum(pv.power_kw for pv in self._pv_units)
        load_total = sum(c.power_kw for c in self._chargers)
        battery_power = self._battery.power_kw
        battery_soc = self._battery.soc or 50.0
        grid_power = load_total - pv_total - battery_power

        self._state = SystemState(
            timestamp=self._timestamp,
            simulated_hour=self._simulated_hour,
            pv_power=round(pv_total, 2),
            load_power=round(load_total, 2),
            storage_power=round(battery_power, 2),
            storage_soc=round(battery_soc, 2),
            grid_power=round(grid_power, 2),
            pv_units=[pv.model_copy(deep=True) for pv in self._pv_units],
            chargers=[c.model_copy(deep=True) for c in self._chargers],
            battery=self._battery.model_dump(),
            grid=self._grid.model_dump(),
        )

    def _next_environment(self) -> None:
        """推进一个时间步（15min）"""
        self._simulated_hour = (self._simulated_hour + self._simulation_step_hours) % 24.0
        self._timestamp = datetime.now()

        hour = self._simulated_hour
        if 6.0 <= hour <= 18.0:
            daylight_position = (hour - 6.0) / 12.0
            base_pv = 90.0 * math.sin(math.pi * daylight_position)
        else:
            base_pv = 0.0

        cloud_factor = 0.85 + self._random.uniform(0, 0.30)
        base_pv = base_pv * cloud_factor
        base_pv = max(0.0, round(base_pv, 2))

        base_load = (
            58.0
            + 12.0 * math.sin((hour - 8.0) / 24.0 * 2.0 * math.pi)
            + self._random.uniform(-4.0, 4.0)
        )
        base_load = max(30.0, round(base_load, 2))

        self._update_pv_units(base_pv)
        self._update_chargers(base_load)
        self._update_grid()
        self._update_aggregate_state()

    # ==================== A-P0-02: 历史保存已迁移至 DeviceRuntimeService ====================
    # _save_device_history() 已删除。
    # 历史保存职责已统一由 DeviceRuntimeService 承担：
    # - generate_history() 使用 telemetry_repo.add_many()
    # - execute() 使用 telemetry_repo.add_many()

    def reset(self, seed: Optional[int] = None) -> SystemState:
        """
        重置模拟器到初始状态

        Args:
            seed: 随机种子（默认 None 表示使用 2026）
        """
        with self._lock:
            if seed is not None:
                self._random.seed(seed)
            else:
                self._random.seed(2026)

            self._simulated_hour = 6.0
            self._timestamp = datetime.now()

            for pv in self._pv_units:
                pv.power_kw = 0.0
                pv.current_a = 0.0
                pv.voltage_v = 220.0 + self._random.uniform(-5, 5)
                pv.temperature_c = 25.0 + self._random.uniform(-3, 3)
                pv.energy_kwh = 0.0
                pv.timestamp = self._timestamp
                pv.is_online = True
                pv.quality = "good"

            for charger in self._chargers:
                charger.power_kw = 0.0
                charger.current_a = 0.0
                charger.enabled = True
                charger.status = "idle"
                charger.connected = False
                charger.energy_kwh = 0.0
                charger.timestamp = self._timestamp
                charger.is_online = True
                charger.quality = "good"

            self._battery.power_kw = 0.0
            self._battery.soc = 50.0
            self._battery.soh = 98.0
            self._battery.energy_kwh = 200.0
            self._battery.timestamp = self._timestamp
            self._battery.is_online = True
            self._battery.quality = "good"
            self._battery.alarm = False

            self._grid.power_kw = 0.0
            self._grid.current_a = 0.0
            self._grid.energy_kwh = 0.0
            self._grid.timestamp = self._timestamp
            self._grid.is_online = True
            self._grid.quality = "good"

            self._update_aggregate_state()
            return self._state.model_copy(deep=True)

    def get_state_without_advance(self) -> SystemState:
        """获取当前系统状态（不推进时间）"""
        with self._lock:
            return self._state.model_copy(deep=True)

    def get_all_devices_state(self) -> List[DeviceRuntimeState]:
        """获取所有 12 个设备的当前状态列表"""
        with self._lock:
            result = []
            # 5 路 PV
            for pv in self._pv_units:
                result.append(pv.model_copy(deep=True))
            # 5 个充电桩
            for c in self._chargers:
                result.append(c.model_copy(deep=True))
            # Battery
            result.append(self._battery.model_copy(deep=True))
            # Grid
            result.append(self._grid.model_copy(deep=True))
            return result

    def get_current_timestamp(self) -> datetime:
        """获取当前仿真时间戳（A-P0-03）"""
        with self._lock:
            return self._timestamp

    def step_with_control(
        self,
        storage_power_target: float = 0.0,
        charger_targets: Optional[List[dict]] = None,
    ) -> SystemState:
        """
        推进一个仿真步长（15min），同时应用控制决策。

        用于 A11 批量历史生成：每个时间步更新环境 + 应用控制。
        不自动保存历史（由调用方批量保存以提升性能）。

        Args:
            storage_power_target: 储能目标功率（正=放电，负=充电）
            charger_targets: 充电桩控制列表，格式 [{"device_code": "CHG001", "enabled": bool}]

        Returns:
            SystemState: 更新后的系统状态
        """
        with self._lock:
            # 1. 推进环境（PV/负荷变化）
            self._next_environment()

            # 2. 应用储能控制
            if storage_power_target != 0.0:
                target = max(-10.0, min(10.0, storage_power_target))
                delta_soc = (
                    -target
                    * self._simulation_step_hours
                    / (self._battery.energy_kwh or 200.0)
                    * 100.0
                )
                current_soc = self._battery.soc or 50.0
                new_soc = max(0.0, min(100.0, current_soc + delta_soc))

                if new_soc <= 0.0 and target > 0:
                    target = 0.0
                if new_soc >= 100.0 and target < 0:
                    target = 0.0

                self._battery.power_kw = round(target, 2)
                self._battery.soc = round(new_soc, 2)
                self._battery.timestamp = self._timestamp

            # 3. 应用充电桩控制（若有）
            if charger_targets:
                for ct in charger_targets:
                    device_code = ct.get("device_code")
                    enabled = ct.get("enabled")
                    if device_code and enabled is not None:
                        for charger in self._chargers:
                            if charger.device_code == device_code:
                                charger.enabled = enabled
                                if not enabled:
                                    charger.power_kw = 0.0
                                    charger.status = "disabled"
                                    charger.current_a = 0.0
                                    charger.connected = False
                                else:
                                    charger.status = "idle"
                                    charger.connected = False
                                charger.timestamp = self._timestamp
                                break

            # 4. 更新电网（功率平衡）
            self._update_grid()

            # 5. 更新聚合状态
            self._update_aggregate_state()

            return self._state.model_copy(deep=True)

    # ==================== 以下为原接口保持不变 ====================

    def read_state(self) -> SystemState:
        """
        读取当前状态（纯只读，不推进时间）
        为了向后兼容保留此方法，内部调用 get_state_without_advance()
        """
        return self.get_state_without_advance()

    def get_pv_units(self) -> List[DeviceRuntimeState]:
        with self._lock:
            return [pv.model_copy(deep=True) for pv in self._pv_units]

    def get_chargers(self) -> List[DeviceRuntimeState]:
        with self._lock:
            return [c.model_copy(deep=True) for c in self._chargers]

    def get_battery(self) -> DeviceRuntimeState:
        with self._lock:
            return self._battery.model_copy(deep=True)

    def get_grid(self) -> DeviceRuntimeState:
        with self._lock:
            return self._grid.model_copy(deep=True)

    def execute_command(self, decision: ControlDecision) -> SystemState:
        with self._lock:
            target = max(-10.0, min(10.0, decision.storage_power_target))

            delta_soc = (
                -target
                * self._simulation_step_hours
                / (self._battery.energy_kwh or 200.0)
                * 100.0
            )
            current_soc = self._battery.soc or 50.0
            new_soc = max(0.0, min(100.0, current_soc + delta_soc))

            if new_soc <= 0.0 and target > 0:
                target = 0.0
            if new_soc >= 100.0 and target < 0:
                target = 0.0

            self._battery.power_kw = round(target, 2)
            self._battery.soc = round(new_soc, 2)
            self._battery.timestamp = self._timestamp

            self._update_grid()
            self._update_aggregate_state()

            return self._state.model_copy(deep=True)

    def set_charger_enabled(self, device_code: str, enabled: bool) -> bool:
        """设置充电桩启用/禁用（用于手动控制）"""
        print(f"[Simulator] set_charger_enabled: {device_code} -> {enabled}")
        with self._lock:
            for charger in self._chargers:
                if charger.device_code == device_code:
                    charger.enabled = enabled
                    if not enabled:
                        charger.power_kw = 0.0
                        charger.status = "disabled"
                        charger.current_a = 0.0
                        charger.connected = False
                    else:
                        charger.status = "idle"
                        charger.connected = False
                    charger.timestamp = self._timestamp
                    self._update_grid()
                    self._update_aggregate_state()
                    print(f"[Simulator] ✅ 已更新: {device_code} -> enabled={charger.enabled}, power={charger.power_kw}")
                    return True
            print(f"[Simulator] ❌ 未找到设备: {device_code}")
            return False