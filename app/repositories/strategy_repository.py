# app/repositories/strategy_repository.py
"""
策略配置 Repository
负责策略配置的数据访问和默认初始化
"""
from sqlalchemy.orm import Session
from app.models.strategy import StrategyConfigModel


class StrategyRepository:
    """策略配置数据访问层"""

    def __init__(self, db: Session):
        self.db = db

    def get_active_config(self) -> StrategyConfigModel | None:
        """获取当前激活的策略配置"""
        return self.db.query(StrategyConfigModel).filter(
            StrategyConfigModel.is_active == True
        ).first()

    def get_by_name(self, config_name: str) -> StrategyConfigModel | None:
        """根据配置名称查询"""
        return self.db.query(StrategyConfigModel).filter(
            StrategyConfigModel.config_name == config_name
        ).first()

    def get_by_id(self, config_id: int) -> StrategyConfigModel | None:
        """根据 ID 查询"""
        return self.db.query(StrategyConfigModel).filter(
            StrategyConfigModel.id == config_id
        ).first()

    def update_active_config(
            self,
            config_name: str,
            soc_min: float,
            soc_max: float,
            charge_power_kw: float,
            discharge_power_kw: float,
            is_active: bool = True,
    ) -> StrategyConfigModel:
        """
        更新激活配置（幂等操作）
        - 有激活配置 → 原地更新
        - 无激活配置但有同名配置 → 更新并激活
        - 没有任何配置 → 新建
        """
        # 1. 先查找激活配置
        config = self.get_active_config()

        # 2. 如果没有激活配置，按名称查找
        if config is None:
            config = self.get_by_name(config_name)

        # 3. 如果仍然没有，创建新配置
        if config is None:
            config = StrategyConfigModel(
                config_name=config_name,
                soc_min=soc_min,
                soc_max=soc_max,
                charge_power_kw=charge_power_kw,
                discharge_power_kw=discharge_power_kw,
                is_active=is_active,
            )
            self.db.add(config)
        else:
            # 4. 存在则原地更新
            config.config_name = config_name
            config.soc_min = soc_min
            config.soc_max = soc_max
            config.charge_power_kw = charge_power_kw
            config.discharge_power_kw = discharge_power_kw
            config.is_active = is_active

        self.db.flush()
        self.db.refresh(config)
        return config

    def ensure_default_config(self) -> StrategyConfigModel:
        """
        幂等初始化默认配置
        如果没有任何配置，创建默认配置
        如果已有配置，不做任何操作
        """
        existing = self.db.query(StrategyConfigModel).first()
        if existing:
            return existing

        default_config = StrategyConfigModel(
            config_name="default",
            soc_min=20.0,
            soc_max=90.0,
            charge_power_kw=10.0,
            discharge_power_kw=10.0,
            is_active=True,
        )
        self.db.add(default_config)
        self.db.commit()
        self.db.refresh(default_config)
        return default_config