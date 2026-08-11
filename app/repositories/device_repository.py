from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.device import Device


class DeviceRepository:
    """设备数据访问层"""

    def __init__(self, db: Session):
        self.db = db

    def list_devices(self, device_type: Optional[str] = None) -> List[Device]:
        """获取设备列表，可按类型筛选"""
        query = self.db.query(Device)
        if device_type:
            query = query.filter(Device.device_type == device_type)
        return query.all()

    def get_by_id(self, device_id: int) -> Optional[Device]:
        """根据 ID 获取设备"""
        return self.db.query(Device).filter(Device.id == device_id).first()

    def get_by_code(self, device_code: str) -> Optional[Device]:
        """根据设备编码获取设备"""
        return self.db.query(Device).filter(Device.device_code == device_code).first()

    def ensure_default_devices(self) -> List[Device]:
        """
        幂等初始化默认设备。
        如果设备已存在则跳过，不存在则创建。
        返回所有默认设备列表。
        """
        default_devices = [
            {"device_code": "PV001", "device_name": "模拟光伏", "device_type": "pv"},
            {"device_code": "ESS001", "device_name": "模拟储能", "device_type": "storage"},
            {"device_code": "CHG001", "device_name": "模拟充电负载", "device_type": "charger"},
        ]

        created = []
        for data in default_devices:
            existing = self.get_by_code(data["device_code"])
            if not existing:
                device = Device(
                    device_code=data["device_code"],
                    device_name=data["device_name"],
                    device_type=data["device_type"],
                    is_online=True,
                )
                self.db.add(device)
                created.append(device)
            else:
                created.append(existing)

        self.db.commit()
        return created