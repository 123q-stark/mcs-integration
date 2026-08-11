from __future__ import annotations

import math
import random
import threading
from datetime import datetime

from app.devices.base import DeviceAdapter
from app.schemas import ControlDecision, SystemState


class SimulatorAdapter(DeviceAdapter):
    """用少量公式模拟光伏、负载和储能状态。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._random = random.Random(2026)
        self._storage_capacity_kwh = 200.0
        self._simulation_step_hours = 0.25
        self._state = self._initial_state()

    def _initial_state(self) -> SystemState:
        return SystemState(
            timestamp=datetime.now(),
            simulated_hour=6.0,
            pv_power=0.0,
            load_power=55.0,
            storage_power=0.0,
            storage_soc=50.0,
        )

    def _next_environment(self) -> None:
        hour = (self._state.simulated_hour + self._simulation_step_hours) % 24.0

        # 6:00—18:00 使用正弦曲线表示白天光伏变化。
        if 6.0 <= hour <= 18.0:
            daylight_position = (hour - 6.0) / 12.0
            pv_power = 90.0 * math.sin(math.pi * daylight_position)
        else:
            pv_power = 0.0

        pv_power += self._random.uniform(-2.5, 2.5)
        pv_power = max(0.0, round(pv_power, 2))

        # 负载只做平滑变化和轻微随机扰动，不模拟具体车辆。
        load_power = (
            58.0
            + 12.0 * math.sin((hour - 8.0) / 24.0 * 2.0 * math.pi)
            + self._random.uniform(-4.0, 4.0)
        )
        load_power = max(30.0, round(load_power, 2))

        self._state = self._state.model_copy(
            update={
                "timestamp": datetime.now(),
                "simulated_hour": hour,
                "pv_power": pv_power,
                "load_power": load_power,
            }
        )

    def read_state(self) -> SystemState:
        with self._lock:
            self._next_environment()
            return self._state.model_copy(deep=True)

    def execute_command(self, decision: ControlDecision) -> SystemState:
        with self._lock:
            target = max(-10.0, min(10.0, decision.storage_power_target))

            # 正值表示放电，负值表示充电。
            delta_soc = (
                -target
                * self._simulation_step_hours
                / self._storage_capacity_kwh
                * 100.0
            )
            new_soc = max(0.0, min(100.0, self._state.storage_soc + delta_soc))

            # 达到边界时不再继续充放电。
            if new_soc <= 0.0 and target > 0:
                target = 0.0
            if new_soc >= 100.0 and target < 0:
                target = 0.0

            self._state = self._state.model_copy(
                update={
                    "timestamp": datetime.now(),
                    "storage_power": round(target, 2),
                    "storage_soc": round(new_soc, 2),
                }
            )
            return self._state.model_copy(deep=True)

    def reset(self) -> SystemState:
        with self._lock:
            self._random.seed(2026)
            self._state = self._initial_state()
            return self._state.model_copy(deep=True)