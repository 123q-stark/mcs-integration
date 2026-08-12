"""
策略配置 API
提供策略配置的查询、更新和预览接口
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.repositories.price_repository import PriceRepository
from app.repositories.grid_strategy_repository import GridStrategyRepository
from app.repositories.strategy_device_repository import StrategyDeviceRepository
from app.schemas.strategy import (
    StrategyConfigResponse,
    StrategyConfigUpdate,
    StrategyPreviewRequest,
    StrategyPreviewResponse,
    PriceConfigResponse,
    PriceConfigUpdate,
    GridStrategyConfigResponse,
    GridStrategyConfigUpdate,
    ModeResponse,
    ModeUpdate,
)
from app.services.strategy_service import StrategyService
from app.services.strategy_runtime_service import StrategyRuntimeService  # B-09 新增

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ============ 策略配置 API ============

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
        logger.exception("策略预览失败")
        raise HTTPException(
            status_code=500,
            detail="策略预览失败，请检查输入或服务器日志。",
        )


# ============ 电价配置 API（B-03） ============

@router.get("/price-config", response_model=PriceConfigResponse)
async def get_price_config(request: Request):
    """
    获取当前电价配置
    """
    database = request.app.state.database
    with database.session() as db:
        repo = PriceRepository(db)
        return repo.get_config()


@router.put("/price-config", response_model=PriceConfigResponse)
async def update_price_config(
    request: Request,
    update_data: PriceConfigUpdate,
):
    """
    更新电价配置（支持部分更新）
    """
    try:
        database = request.app.state.database
        with database.session() as db:
            repo = PriceRepository(db)
            return repo.update_config(
                valley_price=update_data.valley_price,
                flat_price=update_data.flat_price,
                peak_price=update_data.peak_price,
            )
    except Exception as e:
        logger.exception("更新电价配置失败")
        raise HTTPException(
            status_code=500,
            detail="电价配置保存失败，请检查服务器日志。",
        )


# ============ 电网策略配置 API（B-04） ============

@router.get("/grid-config", response_model=GridStrategyConfigResponse)
async def get_grid_config(request: Request):
    """
    获取当前电网策略配置
    """
    database = request.app.state.database
    with database.session() as db:
        repo = GridStrategyRepository(db)
        return repo.get_config()


@router.put("/grid-config", response_model=GridStrategyConfigResponse)
async def update_grid_config(
    request: Request,
    update_data: GridStrategyConfigUpdate,
):
    """
    更新电网策略配置（支持部分更新）
    """
    try:
        database = request.app.state.database
        with database.session() as db:
            repo = GridStrategyRepository(db)
            return repo.update_config(
                max_import_power_kw=update_data.max_import_power_kw,
                allow_export=update_data.allow_export,
                max_export_power_kw=update_data.max_export_power_kw,
            )
    except Exception as e:
        logger.exception("更新电网策略配置失败")
        raise HTTPException(
            status_code=500,
            detail="电网策略配置保存失败，请检查服务器日志。",
        )


# ============ 设备策略配置 API（B-02） ============

@router.get("/device-configs")
async def get_device_configs(request: Request):
    """
    获取所有设备的策略配置（10条：PV001~PV005, CHG001~CHG005）
    """
    database = request.app.state.database
    with database.session() as db:
        repo = StrategyDeviceRepository(db)
        configs = repo.get_all()
        return [
            {
                "device_code": c.device_code,
                "participate_in_strategy": c.participate_in_strategy,
                "allow_strategy_control": c.allow_strategy_control,
                "strategy_power_limit_kw": c.strategy_power_limit_kw,
                "priority": c.priority,
            }
            for c in configs
        ]


@router.get("/device-configs/{device_code}")
async def get_device_config(request: Request, device_code: str):
    """
    获取单个设备的策略配置
    """
    database = request.app.state.database
    with database.session() as db:
        repo = StrategyDeviceRepository(db)
        config = repo.get_by_device_code(device_code)
        if config is None:
            raise HTTPException(status_code=404, detail="设备策略配置不存在")
        return {
            "device_code": config.device_code,
            "participate_in_strategy": config.participate_in_strategy,
            "allow_strategy_control": config.allow_strategy_control,
            "strategy_power_limit_kw": config.strategy_power_limit_kw,
            "priority": config.priority,
        }


@router.put("/device-configs/{device_code}")
async def update_device_config(
    request: Request,
    device_code: str,
    update_data: dict,
):
    """
    更新单个设备的策略配置
    支持部分更新，可传入以下字段：
        participate_in_strategy (bool)
        allow_strategy_control (bool)
        strategy_power_limit_kw (float, optional)
        priority (int)
    """
    database = request.app.state.database
    with database.session() as db:
        repo = StrategyDeviceRepository(db)
        config = repo.update(device_code, update_data)
        if config is None:
            raise HTTPException(status_code=404, detail="设备策略配置不存在")
        return {
            "device_code": config.device_code,
            "participate_in_strategy": config.participate_in_strategy,
            "allow_strategy_control": config.allow_strategy_control,
            "strategy_power_limit_kw": config.strategy_power_limit_kw,
            "priority": config.priority,
        }


# ============ 模式切换 API（B-06） ============

@router.get("/mode", response_model=ModeResponse)
async def get_mode(request: Request):
    """
    获取当前模式（requested_mode 和 effective_mode）
    """
    database = request.app.state.database
    with database.session() as db:
        from app.repositories.strategy_repository import StrategyRepository
        repo = StrategyRepository(db)
        config = repo.get_active_config()
        if config is None:
            raise HTTPException(status_code=404, detail="未找到策略配置")
        return ModeResponse(
            requested_mode=config.requested_mode,
            effective_mode=config.requested_mode,  # v1.2 暂时与 requested 一致
            updated_at=config.updated_at,
        )


@router.put("/mode", response_model=ModeResponse)
async def update_mode(
    request: Request,
    update_data: ModeUpdate,
):
    """
    更新请求模式（requested_mode）
    """
    database = request.app.state.database
    with database.session() as db:
        from app.repositories.strategy_repository import StrategyRepository
        repo = StrategyRepository(db)
        config = repo.get_active_config()
        if config is None:
            raise HTTPException(status_code=404, detail="未找到策略配置")
        
        config.requested_mode = update_data.requested_mode
        db.commit()
        db.refresh(config)
        
        return ModeResponse(
            requested_mode=config.requested_mode,
            effective_mode=config.requested_mode,
            updated_at=config.updated_at,
        )


# ============ 策略运行 API（B-09） ============

@router.post("/run")
async def run_strategy(request: Request):
    """
    执行一次完整的策略运行周期
    返回决策结果和执行状态
    """
    try:
        database = request.app.state.database
        
        # 获取设备端口（如果已设置）
        device_read_port = getattr(request.app.state, 'device_read_port', None)
        device_execution_port = getattr(request.app.state, 'device_execution_port', None)
        
        # 创建运行时服务
        runtime = StrategyRuntimeService(
            db=database,
            device_read_port=device_read_port,
            device_execution_port=device_execution_port,
        )
        
        result = runtime.run_cycle()
        
        if result.get("success"):
            return {
                "status": "success",
                "effective_mode": result.get("effective_mode"),
                "fallback_used": result.get("fallback_used"),
                "decision": {
                    "storage_power_target": result["decision"].storage_power_target,
                    "action": result["decision"].action,
                    "message": result["decision"].message,
                    "source": result["decision"].source,
                },
                "execution": {
                    "success": result["execution"].success,
                    "storage_power_actual_kw": result["execution"].storage_power_actual_kw,
                    "message": result["execution"].message,
                },
                "run_id": result.get("run_id"),
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "策略运行失败"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("策略运行失败")
        raise HTTPException(status_code=500, detail=f"策略运行失败: {str(e)}")


@router.get("/runtime")
async def get_runtime_status(request: Request):
    """
    获取当前运行时状态
    """
    database = request.app.state.database
    # 创建一个临时服务实例以获取状态（不执行运行）
    runtime = StrategyRuntimeService(database)
    status = runtime.get_current_status()
    return status