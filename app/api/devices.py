from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.repositories.device_repository import DeviceRepository
from app.services.device_service import DeviceService, DeviceNotFoundError
from app.schemas.device import DeviceSummary, DeviceDetail, DeviceStatusResponse

router = APIRouter(prefix="/api/devices", tags=["devices"])


# ==================== 数据库连接（从应用状态获取） ====================
def get_db(request: Request):
    """从 app.state.database 获取数据库会话"""
    database = request.app.state.database
    with database.session() as db:
        yield db


def get_device_service(db: Session = Depends(get_db)) -> DeviceService:
    repository = DeviceRepository(db)
    return DeviceService(repository)


@router.get("", response_model=list[DeviceSummary])
def list_devices(
        device_type: Optional[str] = None,
        service: DeviceService = Depends(get_device_service),
):
    """
    获取设备列表
    - **device_type**: 可选，按设备类型筛选（pv / storage / charger）
    """
    return service.get_devices(device_type)


@router.get("/{device_id}", response_model=DeviceDetail)
def get_device(
        device_id: int,
        service: DeviceService = Depends(get_device_service),
):
    """
    获取设备详情
    - **device_id**: 设备 ID
    """
    try:
        return service.get_device(device_id)
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备 ID {device_id} 不存在",
        )


# ==================== A-RC2-02: 设备状态读取真实后台状态 ====================
@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
def get_device_status(
        device_id: int,
        request: Request,
        service: DeviceService = Depends(get_device_service),
):
    """
    获取设备实时状态
    - **device_id**: 设备 ID
    - 从后台 EMS 服务读取真实系统状态
    """
    try:
        ems_service = request.app.state.service
        state = ems_service.get_system_state()
        return service.get_device_status(device_id, state)
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备 ID {device_id} 不存在",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="系统尚未初始化，请稍后重试。",
        )


# ==================== 设备历史数据接口 ====================
from app.models import DeviceHistory
from datetime import datetime, timedelta


@router.get("/{device_id}/history")
def get_device_history(
        device_id: int,
        request: Request,
        hours: int = 24,
        db: Session = Depends(get_db),
):
    """
    获取设备历史数据
    - **device_id**: 设备 ID
    - **hours**: 查询过去 N 小时的数据（默认 24）
    """
    # 检查设备是否存在
    repo = DeviceRepository(db)
    device = repo.get_by_id(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备 ID {device_id} 不存在",
        )

    # 查询历史数据
    cutoff_time = datetime.now() - timedelta(hours=hours)
    records = db.query(DeviceHistory).filter(
        DeviceHistory.device_id == device_id,
        DeviceHistory.created_at >= cutoff_time
    ).order_by(DeviceHistory.created_at.asc()).all()

    return {
        "device_id": device_id,
        "device_code": device.device_code,
        "device_type": device.device_type,
        "device_name": device.device_name,
        "data": [
            {
                "time": r.created_at.isoformat(),
                "power_kw": r.power_kw,
                "storage_soc": r.storage_soc,
            }
            for r in records
        ]
    }


# ==================== A-05: 系统实时状态接口 ====================
from app.schemas.common import SystemState


@router.get("/runtime/system-state", response_model=SystemState)
def get_system_state(
    request: Request,
):
    """
    获取完整系统实时状态
    包含 5 路 PV、5 个充电桩、Battery、Grid 的详细状态
    """
    try:
        ems_service = request.app.state.service
        return ems_service.get_system_state()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="系统尚未初始化，请稍后重试。",
        )