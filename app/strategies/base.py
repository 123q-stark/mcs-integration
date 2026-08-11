from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import ControlDecision, SystemState


class EnergyStrategy(ABC):
    """所有规则策略或优化算法都遵守同一个输入输出接口。"""

    @abstractmethod
    def calculate(self, state: SystemState) -> ControlDecision:
        raise NotImplementedError
