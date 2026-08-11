from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import delete, select

from app.database import Database
from app.devices.base import DeviceAdapter
from app.models import ControlCommand, SystemHistory
from app.schemas import (
    CommandItem,
    HistoryItem,
    StatusResponse,
    SystemState,
)
from app.strategies.base import EnergyStrategy
from app.repositories.strategy_repository import StrategyRepository  # 新增


class EMSService:
    """把设备、策略和数据库串成一条完整业务链路。"""

    def __init__(
        self,
        database: Database,
        device: DeviceAdapter,
        strategy: EnergyStrategy,
        loop_seconds: float,
        history_limit: int,
    ) -> None:
        self.database = database
        self.device = device
        self.strategy = strategy
        self.loop_seconds = loop_seconds
        self.history_limit = history_limit

        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._latest_status: StatusResponse | None = None
        self._latest_system_state: SystemState | None = None
    async def run_cycle(self) -> StatusResponse:
        async with self._lock:
            state_before = self.device.read_state()
            
            # 从数据库获取策略配置
            with self.database.session() as db:
                repo = StrategyRepository(db)
                config = repo.get_active_config()
            
            # 将配置传入策略
            decision = self.strategy.calculate(state_before, config)
            state_after = self.device.execute_command(decision)
            self._latest_system_state = state_after.model_copy(deep=True)
            status = StatusResponse(
                pv_power=state_after.pv_power,
                load_power=state_after.load_power,
                storage_power=state_after.storage_power,
                storage_soc=state_after.storage_soc,
                action=decision.action,
                strategy_message=decision.message,
                updated_at=datetime.now(),
            )

            with self.database.session() as db:
                db.add(
                    SystemHistory(
                        created_at=status.updated_at,
                        pv_power=status.pv_power,
                        load_power=status.load_power,
                        storage_power=status.storage_power,
                        storage_soc=status.storage_soc,
                    )
                )
                db.add(
                    ControlCommand(
                        created_at=status.updated_at,
                        command_value=decision.storage_power_target,
                        action=decision.action,
                        strategy_message=decision.message,
                        execute_result="执行成功",
                    )
                )

            self._latest_status = status
            return status

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.loop_seconds,
                )
            except asyncio.TimeoutError:
                await self.run_cycle()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    def get_status(self) -> StatusResponse:
        if self._latest_status is None:
            raise RuntimeError("系统尚未初始化。")
        return self._latest_status

    def get_history(self) -> list[HistoryItem]:
        with self.database.session() as db:
            rows = db.scalars(
                select(SystemHistory)
                .order_by(SystemHistory.id.desc())
                .limit(self.history_limit)
            ).all()
        return [HistoryItem.model_validate(row) for row in reversed(rows)]

    def get_commands(self, limit: int = 10) -> list[CommandItem]:
        with self.database.session() as db:
            rows = db.scalars(
                select(ControlCommand)
                .order_by(ControlCommand.id.desc())
                .limit(limit)
            ).all()
        return [CommandItem.model_validate(row) for row in rows]

    async def reset(self) -> StatusResponse:
        async with self._lock:
            self.device.reset()

            with self.database.session() as db:
                db.execute(delete(SystemHistory))
                db.execute(delete(ControlCommand))

            # 复用一次完整周期，确保重置后页面立即有数据。
            state_before = self.device.read_state()
            
            # 从数据库获取策略配置
            with self.database.session() as db:
                repo = StrategyRepository(db)
                config = repo.get_active_config()
            
            # 将配置传入策略
            decision = self.strategy.calculate(state_before, config)
            state_after = self.device.execute_command(decision)
            self._latest_system_state = state_after.model_copy(deep=True)
            status = StatusResponse(
                pv_power=state_after.pv_power,
                load_power=state_after.load_power,
                storage_power=state_after.storage_power,
                storage_soc=state_after.storage_soc,
                action=decision.action,
                strategy_message=decision.message,
                updated_at=datetime.now(),
            )

            with self.database.session() as db:
                db.add(
                    SystemHistory(
                        created_at=status.updated_at,
                        pv_power=status.pv_power,
                        load_power=status.load_power,
                        storage_power=status.storage_power,
                        storage_soc=status.storage_soc,
                    )
                )
                db.add(
                    ControlCommand(
                        created_at=status.updated_at,
                        command_value=decision.storage_power_target,
                        action=decision.action,
                        strategy_message=decision.message,
                        execute_result="执行成功",
                    )
                )

            self._latest_status = status
            return status
# 在 reset 方法的最后（return status 之后），添加：

    def get_system_state(self) -> SystemState:
        """获取最新的系统状态（深拷贝，不影响内部状态）"""
        if self._latest_system_state is None:
            raise RuntimeError("系统尚未初始化。")
        return self._latest_system_state.model_copy(deep=True)