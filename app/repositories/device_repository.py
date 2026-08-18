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
            # 5 路光伏（A-P1-02: 补齐额定功率）
            {"device_code": "PV001", "device_name": "模拟光伏 #1", "device_type": "pv", "rated_power_kw": 50.0},
            {"device_code": "PV002", "device_name": "模拟光伏 #2", "device_type": "pv", "rated_power_kw": 50.0},
            {"device_code": "PV003", "device_name": "模拟光伏 #3", "device_type": "pv", "rated_power_kw": 50.0},
            {"device_code": "PV004", "device_name": "模拟光伏 #4", "device_type": "pv", "rated_power_kw": 50.0},
            {"device_code": "PV005", "device_name": "模拟光伏 #5", "device_type": "pv", "rated_power_kw": 50.0},
            # 5 个充电桩（A-P1-02: 补齐额定功率）
            {"device_code": "CHG001", "device_name": "充电桩 #1", "device_type": "charger", "rated_power_kw": 50.0},
            {"device_code": "CHG002", "device_name": "充电桩 #2", "device_type": "charger", "rated_power_kw": 50.0},
            {"device_code": "CHG003", "device_name": "充电桩 #3", "device_type": "charger", "rated_power_kw": 50.0},
            {"device_code": "CHG004", "device_name": "充电桩 #4", "device_type": "charger", "rated_power_kw": 50.0},
            {"device_code": "CHG005", "device_name": "充电桩 #5", "device_type": "charger", "rated_power_kw": 50.0},
            # 储能电池（A-P1-02: 补齐额定功率）
            {"device_code": "BATT001", "device_name": "储能电池", "device_type": "battery", "rated_power_kw": 10.0},
            # 电网（A-P1-02: 补齐额定功率）
            {"device_code": "GRID001", "device_name": "电网接入", "device_type": "grid", "rated_power_kw": 300.0},
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
                    rated_power_kw=data.get("rated_power_kw"),  # A-P1-02: 新增
                )
                self.db.add(device)
                created.append(device)
            else:
                # A-P1-02: 如果设备已存在但 rated_power_kw 为 None，补全
                if existing.rated_power_kw is None and data.get("rated_power_kw") is not None:
                    existing.rated_power_kw = data["rated_power_kw"]
                created.append(existing)

        self.db.commit()
        return created