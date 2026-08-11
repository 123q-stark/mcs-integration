"""
电网策略配置 Repository
"""
from sqlalchemy.orm import Session
from app.models.grid_strategy_config import GridStrategyConfigModel


class GridStrategyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_config(self) -> GridStrategyConfigModel:
        config = self.db.query(GridStrategyConfigModel).first()
        if config is None:
            config = GridStrategyConfigModel(
                max_import_power_kw=300.0,
                allow_export=True,
                max_export_power_kw=100.0
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_config(
        self,
        max_import_power_kw=None,
        allow_export=None,
        max_export_power_kw=None
    ) -> GridStrategyConfigModel:
        config = self.get_config()
        if max_import_power_kw is not None:
            config.max_import_power_kw = max_import_power_kw
        if allow_export is not None:
            config.allow_export = allow_export
        if max_export_power_kw is not None:
            config.max_export_power_kw = max_export_power_kw
        self.db.commit()
        self.db.refresh(config)
        return config
