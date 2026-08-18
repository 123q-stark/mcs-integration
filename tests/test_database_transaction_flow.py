"""
A-锁库修复: 验证 execute() 后不会留下锁
"""
import pytest
from datetime import datetime
from app.database import Database, Base
from app.devices.simulator import SimulatorAdapter
from app.services.device_runtime_service import DeviceRuntimeService
from app.models.strategy_run import StrategyRunModel
import tempfile
import os


def test_device_execute_does_not_leave_sqlite_locked():
    """A-锁库修复: execute() 后第二个 Session 能正常写入 strategy_runs"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db_url = f"sqlite:///{path}"

    db = Database(db_url)
    Base.metadata.create_all(bind=db.engine)

    from app.schemas.common import ControlDecision

    simulator = SimulatorAdapter()
    simulator.reset(seed=2026)

    service = DeviceRuntimeService(simulator, db)

    decision = ControlDecision(
        storage_power_target=5.0,
        action="discharge",
        message="测试锁库",
        created_at=datetime.now(),
        source="test",
        mode="TEST"
    )

    # 执行 A execute
    result = service.execute(decision)
    assert result["success"] is True

    # 立即用另一个 Session 写入 strategy_runs（模拟 B）
    try:
        with db.session() as session2:
            run = StrategyRunModel(
                created_at=datetime.now(),
                requested_mode="TEST",
                effective_mode="TEST",
                fallback_used=False,
                storage_power_target=5.0,
                action="discharge",
                message="测试锁库",
                source="test",
                status="success",
            )
            session2.add(run)
            session2.commit()
    except Exception as e:
        pytest.fail(f"数据库被锁定，无法写入 strategy_runs: {e}")

    # 验证 strategy_runs 已写入
    with db.session() as session3:
        count = session3.query(StrategyRunModel).count()
        assert count == 1

    # A-锁库修复: 释放数据库连接后再删除临时文件
    db.engine.dispose()
    os.unlink(path)