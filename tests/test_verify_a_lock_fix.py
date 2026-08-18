import pytest
import sqlite3
import os
from datetime import datetime
from app.database import Database
from app.devices.simulator import SimulatorAdapter
from app.services.device_runtime_service import DeviceRuntimeService
from pydantic import BaseModel
from typing import Optional, List


class ControlDecision(BaseModel):
    storage_power_target: float
    action: str
    message: str
    created_at: datetime
    source: str
    mode: str
    decision_id: Optional[str] = None
    charger_targets: List[dict] = []


def test_a_execution_releases_db_lock():
    db_path = "./test_lock_verify.db"
    
    # 1. 使用 SQLAlchemy 创建数据库和表
    db = Database(f"sqlite:///{db_path}")
    db.create_tables()
    
    # 2. 创建 A 的服务
    device = SimulatorAdapter()
    runtime_service = DeviceRuntimeService(device, db)
    
    # 3. 执行 A 的 execute（写入 telemetry）
    decision = ControlDecision(
        storage_power_target=0.0,
        action="idle",
        message="lock_verification",
        created_at=datetime.now(),
        source="test",
        mode="TEST"
    )
    result = runtime_service.execute(decision)
    
    # 兼容 dict 或对象返回
    if isinstance(result, dict):
        assert result.get("success") is True, "A execute failed"
    else:
        assert result.success is True, "A execute failed"
    
    # 4. ⚠️ 核心验证：使用原生 sqlite3 连接同一个数据库
    #    如果 A 的 execute() 没有释放锁，这里会超时或报错
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP,
                status VARCHAR(50)
            )
        """)
        cursor.execute(
            "INSERT INTO strategy_runs (created_at, status) VALUES (?, ?)",
            (datetime.now().isoformat(), "verification_ok")
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            pytest.fail(f"❌ DATABASE IS STILL LOCKED after A.execute(): {e}")
        raise
    
    # 5. 如果走到这里，说明没有任何锁库异常！
    print("✅ VERIFICATION PASSED: No database is locked. A fix is effective!")
    
    # 清理
    if os.path.exists(db_path):
        os.remove(db_path)
