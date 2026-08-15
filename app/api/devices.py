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
    获取设备实时状态（A-P0-01: 纯只读，不推进时间）
    """
    try:
        ems_service = request.app.state.service
        # A-P0-01: 使用 get_state_without_advance() 代替 read_state()
        # read_state() 会推进时间，违反只读语义
        state = ems_service.device.get_state_without_advance()
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

# ==================== A-06: 设备历史数据接口（使用 DeviceTelemetry） ====================
from app.models.device_telemetry import DeviceTelemetry
from app.repositories.device_telemetry_repository import DeviceTelemetryRepository
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
    - **hours**: 查询过去 N 小时的数据（默认 24，最大 720 = 30天）
    """
    # 1. 检查设备是否存在
    repo = DeviceRepository(db)
    device = repo.get_by_id(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备 ID {device_id} 不存在",
        )

    # 2. 限制查询范围（1~720小时，即15分钟~30天）
    if hours > 720:
        hours = 720
    if hours < 1:
        hours = 1

    # 3. 计算记录数（15分钟步长 = 4条/小时）
    limit = hours * 4

    # 4. 通过 DeviceTelemetryRepository 查询
    telemetry_repo = DeviceTelemetryRepository(db)
    records = telemetry_repo.get_history(
        device_code=device.device_code,
        limit=limit,
    )

    # 5. 构造返回数据
    return {
        "device_id": device_id,
        "device_code": device.device_code,
        "device_type": device.device_type,
        "device_name": device.device_name,
        "data": [
            {
                "time": r.created_at.isoformat(),
                "power_kw": r.power_kw,
                "storage_soc": r.soc,
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


# ==================== A-07: 充电桩手动控制接口 ====================
from pydantic import BaseModel
from typing import Literal


class DeviceControlRequest(BaseModel):
    """设备控制请求"""
    command: Literal["start", "stop"]


@router.post("/{device_id}/control", response_model=dict)
def control_device(
    device_id: int,
    request: Request,
    control_req: DeviceControlRequest,
    db: Session = Depends(get_db),
):
    """
    控制设备（目前仅支持充电桩 start/stop）
    - **device_id**: 设备 ID
    - **command**: start / stop
    """
    print(f"[API] 收到控制请求: device_id={device_id}, command={control_req.command}")

    # 1. 检查设备是否存在且为 charger
    repo = DeviceRepository(db)
    device = repo.get_by_id(device_id)
    if not device:
        print(f"[API] 设备不存在: {device_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"设备 ID {device_id} 不存在",
        )

    if device.device_type != "charger":
        print(f"[API] 设备不是充电桩: {device.device_code}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"设备 {device.device_code} 不是充电桩，无法控制",
        )

    # 2. 获取 Simulator 实例
    ems_service = request.app.state.service
    if ems_service is None:
        print("[API] ❌ ems_service is None")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EMS 服务尚未初始化",
        )

    simulator = ems_service.device
    if simulator is None:
        print("[API] ❌ simulator is None")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="模拟器尚未初始化",
        )

    print(f"[API] 获取到 Simulator: {id(simulator)}")

    # 3. 执行控制命令
    if control_req.command == "start":
        print(f"[API] 准备启动充电桩: {device.device_code}")
        success = simulator.set_charger_enabled(device.device_code, True)
        message = f"充电桩 {device.device_code} 已启用"
    elif control_req.command == "stop":
        print(f"[API] 准备停止充电桩: {device.device_code}")
        success = simulator.set_charger_enabled(device.device_code, False)
        message = f"充电桩 {device.device_code} 已停用"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的命令: {control_req.command}",
        )

    print(f"[API] set_charger_enabled 返回: {success}")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"控制充电桩 {device.device_code} 失败",
        )

    # 重新获取最新状态（验证是否已更改）
    updated_chargers = simulator.get_chargers()
    for c in updated_chargers:
        if c.device_code == device.device_code:
            print(f"[API] 更新后状态: {c.device_code} -> enabled={c.enabled}, power={c.power_kw}")

    return {
        "success": True,
        "message": message,
        "device_code": device.device_code,
        "command": control_req.command,
    }


# ==================== A-11: 快速历史生成 ====================
from pydantic import BaseModel, Field
from app.services.device_runtime_service import DeviceRuntimeService
from app.repositories.device_telemetry_repository import DeviceTelemetryRepository
import os


class GenerateHistoryRequest(BaseModel):
    """快速历史生成请求"""
    days: int = Field(30, ge=1, le=365, description="生成天数（1~365）")
    seed: int = Field(2026, description="随机种子，确保可复现")


def get_telemetry_repo(db: Session = Depends(get_db)) -> DeviceTelemetryRepository:
    """获取设备遥测 Repository"""
    return DeviceTelemetryRepository(db)


def get_runtime_service(
    request: Request,
    telemetry_repo: DeviceTelemetryRepository = Depends(get_telemetry_repo),
) -> DeviceRuntimeService:
    """
    获取设备运行时服务
    依赖：
    - request.app.state.service.device (SimulatorAdapter)
    - telemetry_repo (DeviceTelemetryRepository)
    """
    ems_service = request.app.state.service
    if ems_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EMS 服务尚未初始化",
        )
    simulator = ems_service.device
    if simulator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="模拟器尚未初始化",
        )
    return DeviceRuntimeService(simulator, telemetry_repo)


@router.post("/simulator/generate-history")
def generate_history(
    req: GenerateHistoryRequest,
    service: DeviceRuntimeService = Depends(get_runtime_service),
):
    """
    快速生成历史数据（仅 Simulator 阶段可用）

    生成指定天数的历史遥测数据，每个时刻包含 12 个逻辑设备的状态。
    使用固定随机种子确保可复现。

    - **days**: 生成天数（默认 30，最大 365）
    - **seed**: 随机种子（默认 2026）

    生成数据包括：
    - 每个时刻 12 个逻辑设备（5 PV + 5 Charger + 1 Battery + 1 Grid）的遥测记录
    - 功率平衡（grid = load - pv - storage）
    - SOC 合理递推

    返回：
    - success: 是否成功
    - total_steps: 生成的总时刻数
    - total_records: 生成的遥测记录总数（= total_steps * 12）
    - message: 结果描述
    """
    # 仅允许开发/Simulator 模式
    env = os.getenv("ENV", "development")
    if env not in ("development", "test", "simulator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"历史生成接口仅在开发/Simulator 模式下可用（当前 ENV={env}）",
        )

    try:
        result = service.generate_history(req.days, req.seed)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成历史数据失败: {str(e)}",
        )