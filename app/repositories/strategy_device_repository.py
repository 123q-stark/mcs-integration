"""
设备策略配置 Repository
负责策略设备配置的数据访问和默认初始化
"""
from sqlalchemy.orm import Session
from app.models.strategy_device_config import StrategyDeviceConfigModel


class StrategyDeviceRepository:
    """设备策略配置数据访问层"""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self):
        """获取所有设备策略配置"""
        return self.db.query(StrategyDeviceConfigModel).order_by(
            StrategyDeviceConfigModel.device_code
        ).all()

    def get_by_device_code(self, device_code: str):
        """根据设备编码查询"""
        return self.db.query(StrategyDeviceConfigModel).filter(
            StrategyDeviceConfigModel.device_code == device_code
        ).first()

    def update(self, device_code: str, data: dict):
        """更新指定设备的策略配置"""
        config = self.get_by_device_code(device_code)
        if not config:
            return None
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.db.commit()
        self.db.refresh(config)
        return config

    def init_default_configs(self):
        """
        初始化默认设备策略配置（逐设备幂等）
        为 PV001~PV005 和 CHG001~CHG005 创建配置
        存在则跳过，不存在则补建
        """
        # 目标设备列表
        pv_codes = [f"PV00{i}" for i in range(1, 6)]
        charger_codes = [f"CHG00{i}" for i in range(1, 6)]
        all_codes = pv_codes + charger_codes

        for device_code in all_codes:
            existing = self.get_by_device_code(device_code)
            if existing is not None:
                continue  # 已存在，跳过

            # 不存在，创建
            if device_code.startswith("PV"):
                config = StrategyDeviceConfigModel(
                    device_code=device_code,
                    participate_in_strategy=True,
                    allow_strategy_control=False,
                    strategy_power_limit_kw=None,
                    priority=1,
                )
            else:  # CHG
                # 提取数字后缀作为优先级 (CHG001 -> 1)
                priority = int(device_code[-3:])
                config = StrategyDeviceConfigModel(
                    device_code=device_code,
                    participate_in_strategy=True,
                    allow_strategy_control=True,
                    strategy_power_limit_kw=50.0,
                    priority=priority,
                )
            self.db.add(config)

        self.db.commit()
