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


# ============ 设备策略配置 API（B-02） ============

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


@router.put("/device-configs/{device_code}")
async def update_device_config(request: Request, device_code: str, update_data: dict):
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
    database = request.app.state.database
    with database.session() as db:
        from app.repositories.strategy_repository import StrategyRepository
        repo = StrategyRepository(db)
        config = repo.get_active_config()
        if config is None:
            raise HTTPException(status_code=404, detail="未找到策略配置")
        return ModeResponse(
            requested_mode=config.requested_mode,
            effective_mode=config.requested_mode,
            updated_at=config.updated_at,
        )


@router.put("/mode", response_model=ModeResponse)
async def update_mode(request: Request, update_data: ModeUpdate):
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
            # ===== B-P1-03: 统一 decision 字段，返回完整 dict =====
            decision_dict = result["decision"].dict() if hasattr(result["decision"], 'dict') else result["decision"]
            return {
                "status": "success",
                "effective_mode": result.get("effective_mode"),
                "fallback_used": result.get("fallback_used"),
                "decision": decision_dict,
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
    database = request.app.state.database
    runtime = StrategyRuntimeService(database)
    status = runtime.get_current_status()
    return status


# ============ 预测数据 API（v1.3 + B-P1-07） ============

@router.get("/forecast/load")
async def get_load_forecast(request: Request):
    """
    获取最新的负荷预测（96 点）
    如果没有真实预测数据，返回 available: false
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
            # B-P1-04: 统一转换为 value_kw
            if points and "value" in points[0] and "value_kw" not in points[0]:
                points = [{"timestamp": p["timestamp"], "value_kw": p["value"]} for p in points]
            return {
                "available": True,
                "model_name": "XGBoost",
                "target": "load",
                "created_at": record.created_at.isoformat(),
                "step_minutes": 15,
                "points": points,
                "mae": None,
                "rmse": None
            }
    
    # ===== B-P1-07: 去掉 Simulated 假结果 =====
    return {
        "available": False,
        "reason": "暂无负荷预测数据，请先运行策略生成预测",
        "points": []
    }


@router.get("/forecast/pv")
async def get_pv_forecast(request: Request):
    """
    获取最新的 PV 预测（96 点）
    如果没有真实预测数据，返回 available: false
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
            # B-P1-04: 统一转换为 value_kw
            if points and "value" in points[0] and "value_kw" not in points[0]:
                points = [{"timestamp": p["timestamp"], "value_kw": p["value"]} for p in points]
            return {
                "available": True,
                "model_name": "XGBoost",
                "target": "pv",
                "created_at": record.created_at.isoformat(),
                "step_minutes": 15,
                "points": points,
                "mae": None,
                "rmse": None
            }
    
    # ===== B-P1-07: 去掉 Simulated 假结果 =====
    return {
        "available": False,
        "reason": "暂无PV预测数据，请先运行策略生成预测",
        "points": []
    }


# ============ 调度计划 API（v1.4） ============

@router.get("/schedule")
async def get_schedule(request: Request):
    """
    获取最新的储能调度计划（96 点）
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
    
    # ===== B-P1-07: 去掉 Simulated 假结果 =====
    return {
        "available": False,
        "reason": "暂无调度计划数据，请先运行策略生成调度",
        "schedule": []
    }