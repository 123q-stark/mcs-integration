"""
策略运行记录 Repository
职责：仅负责 strategy_runs 表的 CRUD，不自建 Engine
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from app.models.strategy_run import StrategyRunModel

logger = logging.getLogger(__name__)


class StrategyRunRepository:
    """策略运行记录 Repository（只接收 Session，不自建 Engine）"""

    def __init__(self, session):
        """只接收 Session 对象，不自行创建 Database"""
        self.session = session

    def create(self, data: Dict[str, Any]) -> StrategyRunModel:
        """
        创建一条策略运行记录
        data 应包含所有 StrategyRunModel 字段
        """
        run = StrategyRunModel(**data)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_by_id(self, run_id: int) -> Optional[StrategyRunModel]:
        return self.session.query(StrategyRunModel).filter(
            StrategyRunModel.id == run_id
        ).first()

    def get_latest(self) -> Optional[StrategyRunModel]:
        return self.session.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).first()

    def get_all(self, limit: int = 100) -> list[StrategyRunModel]:
        return self.session.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).limit(limit).all()

    def get_by_status(self, status: str, limit: int = 50) -> list[StrategyRunModel]:
        return self.session.query(StrategyRunModel).filter(
            StrategyRunModel.status == status
        ).order_by(
            StrategyRunModel.created_at.desc()
        ).limit(limit).all()
