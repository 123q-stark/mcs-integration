"""
策略配置业务服务
负责策略配置的获取、更新和预览
"""
from sqlalchemy.orm import Session
from app.repositories.strategy_repository import StrategyRepository
from app.schemas.strategy import (
    StrategyConfigResponse,
    StrategyConfigUpdate,
    StrategyPreviewRequest,
    StrategyPreviewResponse,
)
from app.schemas import SystemState, ControlDecision
from app.strategies.fixed_rule import FixedRuleStrategy
from datetime import datetime


class StrategyService:
    """策略配置业务服务"""

    def __init__(self, db: Session):
        self.db = db
        self.repository = StrategyRepository(db)
        self.strategy = FixedRuleStrategy()

    def get_current_config(self) -> StrategyConfigResponse | None:
        """获取当前激活的策略配置"""
        config = self.repository.get_active_config()
        if config is None:
            return None
        return StrategyConfigResponse.model_validate(config)

    def update_current_config(self, request: StrategyConfigUpdate) -> StrategyConfigResponse:
        """
        更新当前策略配置（完整更新）
        先停用所有配置，然后创建新配置
        """
        # ===== 修改点：传递新增字段 =====
        new_config = self.repository.update_active_config(
            config_name=request.config_name,
            soc_min=request.soc_min,
            soc_max=request.soc_max,
            charge_power_kw=request.charge_power_kw,
            discharge_power_kw=request.discharge_power_kw,
            requested_mode=request.requested_mode,           # 新增
            backup_soc_target=request.backup_soc_target,     # 新增
            is_active=True,
        )
        return StrategyConfigResponse.model_validate(new_config)

    def preview_decision(self, request: StrategyPreviewRequest) -> StrategyPreviewResponse:
        """
        预览策略决策
        使用当前活动配置（如果存在），否则使用默认配置
        """
        # 1. 构造 SystemState
        state = SystemState(
            timestamp=datetime.now(),
            pv_power=request.pv_power,
            load_power=request.load_power,
            storage_power=request.storage_power,
            storage_soc=request.storage_soc,
            simulated_hour=12.0,  # 预览时固定为中午
        )

        # 2. 获取当前配置
        config = self.repository.get_active_config()

        # 3. 调用策略生成决策
        decision = self.strategy.calculate(state, config)

        # 4. 转换为预览响应
        return StrategyPreviewResponse(
            storage_power_target=decision.storage_power_target,
            action=decision.action,
            message=decision.message,
            created_at=decision.created_at,
        )