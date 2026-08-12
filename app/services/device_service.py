from typing import List, Optional
from app.repositories.device_repository import DeviceRepository
from app.schemas.device import DeviceSummary, DeviceDetail, DeviceStatusResponse
from app.schemas.common import SystemState


class DeviceNotFoundError(Exception):
    """设备不存在异常"""
    pass


class DeviceService:
    def __init__(self, repository: DeviceRepository):
        """构造函数，接收 Repository 实例"""
        self.repository = repository

    def get_devices(self, device_type: Optional[str] = None) -> List[DeviceSummary]:
        """获取设备列表，转换为响应 Schema"""
        devices = self.repository.list_devices(device_type)
        return [
            DeviceSummary(
                id=d.id,
                device_code=d.device_code,
                device_name=d.device_name,
                device_type=d.device_type,
                is_online=d.is_online,
                rated_power_kw=d.rated_power_kw,
                updated_at=d.updated_at,
            )
            for d in devices
        ]

    def get_device(self, device_id: int) -> DeviceDetail:
        """获取设备详情，不存在时抛出异常"""
        device = self.repository.get_by_id(device_id)
        if not device:
            raise DeviceNotFoundError(f"设备 ID {device_id} 不存在")
        return DeviceDetail(
            id=device.id,
            device_code=device.device_code,
            device_name=device.device_name,
            device_type=device.device_type,
            is_online=device.is_online,
            rated_power_kw=device.rated_power_kw,
            created_at=device.created_at,
            updated_at=device.updated_at,
        )

    # ==================== 设备状态映射（从详细列表查找单个设备） ====================
    def get_device_status(self, device_id: int, state: SystemState) -> DeviceStatusResponse:
        """
        根据设备类型从 SystemState 中查找对应设备的实时状态
        """
        device = self.repository.get_by_id(device_id)
        if not device:
            raise DeviceNotFoundError(f"设备 ID {device_id} 不存在")

        status = None  # 初始化

        # 根据设备类型从 state 的详细列表中获取数据
        if device.device_type == "pv":
            unit = next((u for u in state.pv_units if u.device_code == device.device_code), None)
            power_kw = unit.power_kw if unit else 0.0
            storage_soc = None
        elif device.device_type == "charger":
            unit = next((c for c in state.chargers if c.device_code == device.device_code), None)
            power_kw = unit.power_kw if unit else 0.0
            storage_soc = None
            status = unit.status if unit else None  # ← 新增
        elif device.device_type in ("storage", "battery"):
            if state.battery:
                power_kw = state.battery.get("power_kw", 0.0)
                storage_soc = state.battery.get("soc", None)
            else:
                power_kw = state.storage_power
                storage_soc = state.storage_soc
        elif device.device_type == "grid":
            if state.grid:
                power_kw = state.grid.get("power_kw", 0.0)
                storage_soc = None
            else:
                power_kw = 0.0
                storage_soc = None
        else:
            power_kw = 0.0
            storage_soc = None

        return DeviceStatusResponse(
            device_id=device.id,
            device_code=device.device_code,
            device_type=device.device_type,
            is_online=device.is_online,
            power_kw=power_kw,
            storage_soc=storage_soc,
            updated_at=state.timestamp,
            status=status,  # ← 新增
        )