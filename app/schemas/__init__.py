# app/schemas/__init__.py
from .common import (
    SystemState,
    ControlDecision,
    StatusResponse,
    HistoryItem,
    CommandItem,
    ResetResponse,
)
from .strategy import (  # 新增
    StrategyConfigResponse,
    StrategyConfigUpdate,
    StrategyPreviewRequest,
    StrategyPreviewResponse,
)

__all__ = [
    "SystemState",
    "ControlDecision",
    "StatusResponse",
    "HistoryItem",
    "CommandItem",
    "ResetResponse",
    "StrategyConfigResponse",  # 新增
    "StrategyConfigUpdate",    # 新增
    "StrategyPreviewRequest",  # 新增
    "StrategyPreviewResponse", # 新增
]