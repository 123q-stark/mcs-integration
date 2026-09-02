"""
设备遥测数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from app.models.device_telemetry import DeviceTelemetry


class DeviceTelemetryRepository:
    """设备遥测数据访问层"""

    def __init__(self, db: Session):
        self.db = db

    def add(self, telemetry: DeviceTelemetry) -> DeviceTelemetry:
        """添加单条遥测记录"""
        self.db.add(telemetry)
        self.db.flush()
        return telemetry

    def add_many(self, telemetries: List[DeviceTelemetry]) -> List[DeviceTelemetry]:
        """批量添加遥测记录"""
        for telemetry in telemetries:
            self.db.add(telemetry)
        self.db.flush()
        return telemetries

    def get_history(
        self,
        device_code: str,
        limit: int = 96,
        offset: int = 0,
    ) -> List[DeviceTelemetry]:
        """
        获取设备历史数据（按时间升序）
        - limit: 返回条数，默认96（24小时）
        - offset: 偏移量

        文档要求：04-A-06 返回设备遥测序列，时间升序
        """
        # 步骤1：先按时间倒序获取最新的 limit 条记录的 ID
        ids = (
            self.db.query(DeviceTelemetry.id)
            .filter(DeviceTelemetry.device_code == device_code)
            .order_by(desc(DeviceTelemetry.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        # 提取 ID 列表
        id_list = [row[0] for row in ids]

        if not id_list:
            return []

        # 步骤2：再按时间升序查询这些记录
        return (
            self.db.query(DeviceTelemetry)
            .filter(DeviceTelemetry.id.in_(id_list))
            .order_by(asc(DeviceTelemetry.created_at))
            .all()
        )

    def get_latest(self, device_code: str) -> Optional[DeviceTelemetry]:
        """获取设备最新一条遥测记录"""
        return (
            self.db.query(DeviceTelemetry)
            .filter(DeviceTelemetry.device_code == device_code)
            .order_by(desc(DeviceTelemetry.created_at))
            .first()
        )

    def clear_runtime_history(self) -> None:
        """清空所有遥测历史（用于重置）"""
        self.db.query(DeviceTelemetry).delete()
        self.db.flush()

    def count_by_device(self, device_code: str) -> int:
        """统计某设备的遥测记录数"""
        return (
            self.db.query(DeviceTelemetry)
            .filter(DeviceTelemetry.device_code == device_code)
            .count()
        )