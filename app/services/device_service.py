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

    # ==================== A-06: 设备状态映射 ====================
    def get_device_status(self, device_id: int, state: SystemState) -> DeviceStatusResponse:
        """
        根据设备类型从 SystemState 映射出设备状态
        """
        device = self.repository.get_by_id(device_id)
        if not device:
            raise DeviceNotFoundError(f"设备 ID {device_id} 不存在")

        # 根据设备类型映射功率和 SOC
        if device.device_type == "pv":
            power_kw = state.pv_power
            storage_soc = None
        elif device.device_type in ("storage", "battery"):
            power_kw = state.storage_power
            storage_soc = state.storage_soc
        elif device.device_type == "charger":
            power_kw = state.load_power
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
        )