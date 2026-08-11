"""
电价配置 Repository
负责电价配置的数据访问和默认初始化
"""
from sqlalchemy.orm import Session
from app.models.price_config import PriceConfigModel


class PriceRepository:
    """电价配置数据访问层"""

    def __init__(self, db: Session):
        self.db = db

    def get_config(self) -> PriceConfigModel:
        """
        获取电价配置
        如果不存在，自动创建默认配置
        """
        config = self.db.query(PriceConfigModel).first()
        if config is None:
            config = PriceConfigModel(
                valley_price=0.35,
                flat_price=0.55,
                peak_price=0.85
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_config(self, valley_price: float = None, flat_price: float = None, peak_price: float = None) -> PriceConfigModel:
        """
        更新电价配置
        如果不存在则先创建
        """
        config = self.get_config()

        if valley_price is not None:
            config.valley_price = valley_price
        if flat_price is not None:
            config.flat_price = flat_price
        if peak_price is not None:
            config.peak_price = peak_price

        self.db.commit()
        self.db.refresh(config)
        return config
