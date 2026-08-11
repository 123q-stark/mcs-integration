from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import ControlDecision, SystemState


class DeviceAdapter(ABC):
    """
    设备层统一接口。

    当前由模拟器实现。以后接入 Modbus、MQTT 或其他协议时，
    只需要新增适配器，无需修改策略和业务服务。
    """

    @abstractmethod
    def read_state(self) -> SystemState:
        raise NotImplementedError

    @abstractmethod
    def execute_command(self, decision: ControlDecision) -> SystemState:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> SystemState:
        raise NotImplementedError
