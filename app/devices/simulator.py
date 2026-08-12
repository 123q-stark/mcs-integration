from __future__ import annotations

import math
import random
import threading
from datetime import datetime
from typing import List

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

    # ==================== A-04: 保存设备遥测 ====================
    def _save_device_history(self) -> None:
        """保存所有设备的历史记录到 device_telemetry 表"""
        try:
            from app.database import Database
            from app.config import Settings
            from app.models import Device, DeviceTelemetry

            settings = Settings.from_env()
            db = Database(settings.database_url)

            with db.session() as session:
                devices = session.query(Device).all()
                if not devices:
                    return

                for device in devices:
                    # 根据设备类型从当前状态提取数据
                    if device.device_type == "pv":
                        unit = next((u for u in self._pv_units if u.device_code == device.device_code), None)
                        power_kw = unit.power_kw if unit else 0.0
                        storage_soc = None
                    elif device.device_type == "charger":
                        unit = next((c for c in self._chargers if c.device_code == device.device_code), None)
                        power_kw = unit.power_kw if unit else 0.0
                        storage_soc = None
                    elif device.device_type in ("storage", "battery"):
                        power_kw = self._battery.power_kw
                        storage_soc = self._battery.soc
                    elif device.device_type == "grid":
                        power_kw = self._grid.power_kw
                        storage_soc = None
                    else:
                        continue

                    history = DeviceTelemetry(
                        device_code=device.device_code,
                        device_type=device.device_type,
                        power_kw=power_kw,
                        soc=storage_soc,  # ← 修正字段名
                        quality='good',  # ← 直接赋值
                    )
                    session.add(history)

                session.commit()
                print(f"[Simulator] ✅ 已保存 {len(devices)} 条遥测记录")
        except Exception as e:
            print(f"[Simulator] ❌ 保存设备历史失败: {e}")

    def read_state(self) -> SystemState:
        with self._lock:
            self._next_environment()
            # ===== 新增：保存设备遥测 =====
            self._save_device_history()
            return self._state.model_copy(deep=True)

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

    def reset(self) -> SystemState:
        with self._lock:
            self._random.seed(2026)
            self._simulated_hour = 6.0
            self._timestamp = datetime.now()

            for pv in self._pv_units:
                pv.power_kw = 0.0
                pv.current_a = 0.0
                pv.timestamp = self._timestamp
                pv.is_online = True
                pv.quality = "good"

            for charger in self._chargers:
                charger.power_kw = 0.0
                charger.current_a = 0.0
                charger.enabled = True
                charger.status = "idle"
                charger.connected = False
                charger.timestamp = self._timestamp
                charger.is_online = True
                charger.quality = "good"

            self._battery.power_kw = 0.0
            self._battery.soc = 50.0
            self._battery.timestamp = self._timestamp
            self._battery.is_online = True
            self._battery.quality = "good"
            self._battery.alarm = False

            self._grid.power_kw = 0.0
            self._grid.current_a = 0.0
            self._grid.timestamp = self._timestamp
            self._grid.is_online = True
            self._grid.quality = "good"

            self._update_aggregate_state()
            return self._state.model_copy(deep=True)

    # ============================================================
    # ⚠️ 临时方法（B-09 测试用）- 等待 A 正式实现后删除
    # 正式实现应由 A 在 A-05/A-08 中完成
    # 预计删除时间：A 完成正式实现后
    # ============================================================
    def get_system_state(self):
        """获取当前系统状态（临时实现，用于 B-09 测试）"""
        from app.schemas import SystemState
        from datetime import datetime

        # 尝试从 Simulator 获取真实数据，如果没有则返回默认值
        try:
            pv = getattr(self, 'pv_power', 0.0)
            load = getattr(self, 'load_power', 0.0)
            storage = getattr(self, 'storage_power', 0.0)
            soc = getattr(self, 'storage_soc', 50.0)
            hour = getattr(self, 'simulated_hour', 12.0)
        except:
            pv, load, storage, soc, hour = 0.0, 0.0, 0.0, 50.0, 12.0

        return SystemState(
            timestamp=datetime.now(),
            simulated_hour=hour,
            pv_power=pv,
            load_power=load,
            storage_power=storage,
            storage_soc=soc,
        )

    # ============================================================
    # ⚠️ 临时方法（B-09 测试用）- 等待 A 正式实现后删除
    # 正式实现应由 A 在 A-08 中完成
    # 预计删除时间：A 完成正式实现后
    # ============================================================
    def execute(self, decision):
        """执行控制决策（临时实现，用于 B-09 测试）"""
        from app.schemas import ControlExecutionResult
        from datetime import datetime

        return ControlExecutionResult(
            decision_id=getattr(decision, 'decision_id', None),
            success=True,
            storage_power_actual_kw=decision.storage_power_target,
            charger_results=[],
            message="模拟执行成功（临时实现）",
            executed_at=datetime.now(),
        )