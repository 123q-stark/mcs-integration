"""
电价配置数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime
from app.database import Base


class PriceConfigModel(Base):
    __tablename__ = "price_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    valley_price = Column(Float, default=0.35, nullable=False)
    flat_price = Column(Float, default=0.55, nullable=False)
    peak_price = Column(Float, default=0.85, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<PriceConfig(valley={self.valley_price}, flat={self.flat_price}, peak={self.peak_price})>"
