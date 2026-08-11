# app/api/strategies.py
"""
策略配置 API
提供策略配置的查询、更新和预览接口
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.schemas.strategy import (
    StrategyConfigResponse,
    StrategyConfigUpdate,
    StrategyPreviewRequest,
    StrategyPreviewResponse,
)
from app.services.strategy_service import StrategyService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("/config", response_model=StrategyConfigResponse)
async def get_strategy_config(request: Request):
    """
    获取当前激活的策略配置
    """
    database = request.app.state.database
    with database.session() as db:
        strategy_service = StrategyService(db)
        config = strategy_service.get_current_config()
        if config is None:
            raise HTTPException(
                status_code=404,
                detail="未找到策略配置，请先初始化默认配置"
            )
        return config


@router.put("/config", response_model=StrategyConfigResponse)
async def update_strategy_config(
    request: Request,
    update_data: StrategyConfigUpdate,
):
    """
    更新策略配置（完整更新）
    """
    try:
        database = request.app.state.database
        with database.session() as db:
            strategy_service = StrategyService(db)
            return strategy_service.update_current_config(update_data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # B-RC2-03: 记录完整错误到日志，不暴露给前端
        logger.exception("更新策略配置失败")
        raise HTTPException(
            status_code=500,
            detail="策略配置保存失败，请检查服务器日志。",
        )


@router.post("/preview", response_model=StrategyPreviewResponse)
async def preview_strategy(
    request: Request,
    preview_data: StrategyPreviewRequest,
):
    """
    预览策略决策
    """
    try:
        database = request.app.state.database
        with database.session() as db:
            service = StrategyService(db)
            return service.preview_decision(preview_data)
    except Exception as e:
        # B-RC2-03: 记录完整错误到日志，不暴露给前端
        logger.exception("策略预览失败")
        raise HTTPException(
            status_code=500,
            detail="策略预览失败，请检查输入或服务器日志。",
        )