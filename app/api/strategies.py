"""
策略配置 API
提供策略配置的查询、更新和预览接口
"""
import logging
from datetime import datetime
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
    StrategyDeviceConfigUpdate,  # P1-01 新增
)
from app.services.strategy_service import StrategyService
from app.services.strategy_runtime_service import StrategyRuntimeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ============ 策略配置 API ============

@router.get("/config", response_model=StrategyConfigResponse)
async def get_strategy_config(request: Request):
    database = request.app.state.database
    with database.session() as db:
        strategy_service = StrategyService(db)
        config = strategy_service.get_current_config()
        if config is None:
            raise HTTPException(status_code=404, detail="未找到策略配置")
        return config


@router.put("/config", response_model=StrategyConfigResponse)
async def update_strategy_config(request: Request, update_data: StrategyConfigUpdate):
    try:
        database = request.app.state.database
        with database.session() as db:
            strategy_service = StrategyService(db)
            return strategy_service.update_current_config(update_data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("更新策略配置失败")
        raise HTTPException(status_code=500, detail="策略配置保存失败")


@router.post("/preview", response_model=StrategyPreviewResponse)
async def preview_strategy(request: Request, preview_data: StrategyPreviewRequest):
    try:
        database = request.app.state.database
        with database.session() as db:
            service = StrategyService(db)
            return service.preview_decision(preview_data)
    except Exception as e:
        logger.exception("策略预览失败")
        raise HTTPException(status_code=500, detail="策略预览失败")


# ============ 电价配置 API（B-03） ============

@router.get("/price-config", response_model=PriceConfigResponse)
async def get_price_config(request: Request):
    database = request.app.state.database
    with database.session() as db:
        repo = PriceRepository(db)
        return repo.get_config()


@router.put("/price-config", response_model=PriceConfigResponse)
async def update_price_config(request: Request, update_data: PriceConfigUpdate):
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
        raise HTTPException(status_code=500, detail="电价配置保存失败")


# ============ 电网策略配置 API（B-04） ============

@router.get("/grid-config", response_model=GridStrategyConfigResponse)
async def get_grid_config(request: Request):
    database = request.app.state.database
    with database.session() as db:
        repo = GridStrategyRepository(db)
        return repo.get_config()


@router.put("/grid-config", response_model=GridStrategyConfigResponse)
async def update_grid_config(request: Request, update_data: GridStrategyConfigUpdate):
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
        raise HTTPException(status_code=500, detail="电网策略配置保存失败")


# ============ 设备策略配置 API（B-02 + P1-01） ============

@router.get("/device-configs")
async def get_device_configs(request: Request):
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


# ===== P1-01 修复：使用 StrategyDeviceConfigUpdate Schema 替代裸 dict =====
@router.put("/device-configs/{device_code}")
async def update_device_config(
    request: Request,
    device_code: str,
    update_data: StrategyDeviceConfigUpdate,  # P1-01: 使用 Schema
):
    """
    更新单个设备的策略配置（P1-01：使用 Pydantic 校验）
    支持部分更新，可传入以下字段：
        participate_in_strategy (bool)
        allow_strategy_control (bool)
        strategy_power_limit_kw (float, optional)
        priority (int)
    """
    database = request.app.state.database
    with database.session() as db:
        repo = StrategyDeviceRepository(db)
        # 过滤掉 None 值，只更新传入的字段
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        config = repo.update(device_code, update_dict)
        if config is None:
            raise HTTPException(status_code=404, detail="设备策略配置不存在")
        return {
            "device_code": config.device_code,
            "participate_in_strategy": config.participate_in_strategy,
            "allow_strategy_control": config.allow_strategy_control,
            "strategy_power_limit_kw": config.strategy_power_limit_kw,
            "priority": config.priority,
        }


# ============ 模式切换 API（B-06 + P1-04） ============

@router.get("/mode", response_model=ModeResponse)
async def get_mode(request: Request):
    """
    获取当前模式（P1-04 修复：effective_mode 来自最新策略运行记录）
    """
    database = request.app.state.database
    with database.session() as db:
        from app.repositories.strategy_repository import StrategyRepository
        from app.models.strategy_run import StrategyRunModel

        repo = StrategyRepository(db)
        config = repo.get_active_config()
        if config is None:
            raise HTTPException(status_code=404, detail="未找到策略配置")

        # P1-04: effective_mode 来自最新 strategy_run
        latest_run = db.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).first()

        effective_mode = latest_run.effective_mode if latest_run else None
        updated_at = latest_run.created_at if latest_run else config.updated_at

        return ModeResponse(
            requested_mode=config.requested_mode,
            effective_mode=effective_mode,
            updated_at=updated_at,
        )


@router.put("/mode", response_model=ModeResponse)
async def update_mode(request: Request, update_data: ModeUpdate):
    """
    更新请求模式（P1-01：ModeUpdate 已有枚举校验）
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

        # 获取最新运行记录（保持 effective_mode 不变）
        from app.models.strategy_run import StrategyRunModel
        latest_run = db.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).first()
        effective_mode = latest_run.effective_mode if latest_run else None

        return ModeResponse(
            requested_mode=config.requested_mode,
            effective_mode=effective_mode,
            updated_at=config.updated_at,
        )


# ============ 策略运行 API（B-09） ============

@router.post("/run")
async def run_strategy(request: Request):
    try:
        database = request.app.state.database
        device_read_port = getattr(request.app.state, 'device_read_port', None)
        device_execution_port = getattr(request.app.state, 'device_execution_port', None)

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
                    "success": result["execution"]["success"],
                    "storage_power_actual_kw": result["execution"]["storage_power_actual_kw"],
                    "message": result["execution"]["message"],
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
    """获取最新的策略运行状态（从数据库读取）"""
    database = request.app.state.database
    with database.session() as db:
        from app.models.strategy_run import StrategyRunModel
        from app.repositories.strategy_repository import StrategyRepository

        repo = StrategyRepository(db)
        config = repo.get_active_config()

        latest_run = db.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).first()

        requested_mode = config.requested_mode if config else None
        effective_mode = latest_run.effective_mode if latest_run else requested_mode
        fallback_used = latest_run.fallback_used if latest_run else False
        last_run_at = latest_run.created_at if latest_run else None

        return {
            "requested_mode": requested_mode,
            "effective_mode": effective_mode,
            "fallback_used": fallback_used,
            "last_run_at": last_run_at.isoformat() if last_run_at else None,
            "has_state": latest_run is not None,
            "has_decision": latest_run is not None,
            "has_execution": latest_run is not None,
            "decision": None,
        }


# ============ 预测数据 API（v1.3 + P1-05 修复） ============

@router.get("/forecast/load")
async def get_load_forecast(request: Request):
    """
    获取最新的负荷预测（96 点）
    P1-05: 无真实数据时返回 available=False，不返回 Simulated 假数据
    """
    database = request.app.state.database
    with database.session() as db:
        from app.models.strategy_run import StrategyRunModel
        import json
        record = db.query(StrategyRunModel).filter(
            StrategyRunModel.load_forecast_json.isnot(None)
        ).order_by(StrategyRunModel.created_at.desc()).first()
        if record and record.load_forecast_json:
            points = json.loads(record.load_forecast_json)
            return {
                "available": True,  # P0-01
                "model_name": record.forecast_model_load or "XGBoost",
                "target": "load",
                "created_at": record.created_at.isoformat(),
                "step_minutes": 15,
                "points": points,
                "mae": None,
                "rmse": None
            }

    # P1-05: 无真实数据时返回空，不返回 Simulated 假数据
    return {
        "available": False,
        "model_name": "Unavailable",
        "target": "load",
        "created_at": datetime.now().isoformat(),
        "step_minutes": 15,
        "points": [],
        "mae": None,
        "rmse": None,
        "message": "No valid load forecast found"
    }


@router.get("/forecast/pv")
async def get_pv_forecast(request: Request):
    """
    获取最新的 PV 预测（96 点）
    P1-05: 无真实数据时返回 available=False，不返回 Simulated 假数据
    """
    database = request.app.state.database
    with database.session() as db:
        from app.models.strategy_run import StrategyRunModel
        import json
        record = db.query(StrategyRunModel).filter(
            StrategyRunModel.pv_forecast_json.isnot(None)
        ).order_by(StrategyRunModel.created_at.desc()).first()
        if record and record.pv_forecast_json:
            points = json.loads(record.pv_forecast_json)
            return {
                "available": True,
                "model_name": record.forecast_model_pv or "XGBoost",
                "target": "pv",
                "created_at": record.created_at.isoformat(),
                "step_minutes": 15,
                "points": points,
                "mae": None,
                "rmse": None
            }

    # P1-05: 无真实数据时返回空，不返回 Simulated 假数据
    return {
        "available": False,
        "model_name": "Unavailable",
        "target": "pv",
        "created_at": datetime.now().isoformat(),
        "step_minutes": 15,
        "points": [],
        "mae": None,
        "rmse": None,
        "message": "No valid PV forecast found"
    }


# ============ 调度计划 API（v1.4 + P1-05 修复） ============

@router.get("/schedule")
async def get_schedule(request: Request):
    """
    获取最新的储能调度计划（96 点）
    P1-05: 无真实数据时返回 available=False，不返回 Simulated 假数据
    """
    database = request.app.state.database
    with database.session() as db:
        from app.models.strategy_run import StrategyRunModel
        import json

        record = db.query(StrategyRunModel).filter(
            StrategyRunModel.schedule_json.isnot(None)
        ).order_by(StrategyRunModel.created_at.desc()).first()

        if record and record.schedule_json:
            schedule_data = json.loads(record.schedule_json)
            return {
                "available": True,
                "created_at": record.created_at.isoformat(),
                "schedule": schedule_data,
                "source": record.source,
                "effective_mode": record.effective_mode,
            }

    # P1-05: 无真实数据时返回空，不返回 Simulated 假数据
    return {
        "available": False,
        "created_at": datetime.now().isoformat(),
        "schedule": [],
        "source": None,
        "effective_mode": None,
        "message": "No valid schedule found"
    }