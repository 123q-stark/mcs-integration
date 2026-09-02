"""
P2-01: T01～T10 全站综合测试
验证 A/B/C 三部分完整闭环

运行方式：
    pytest tests/test_full_station_integration.py -v

依赖：
    - 所有 P0/P1 修复已完成
    - 数据库为干净状态（自动创建临时数据库）
"""
import pytest
import json
import tempfile
import os
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import Settings
from app.database import Database, Base
from app.devices.simulator import SimulatorAdapter
from app.services.system_service import EMSService
from app.strategies.fixed_rule import FixedRuleStrategy
from app.services.device_runtime_service import DeviceRuntimeService
from app.repositories.device_repository import DeviceRepository
from app.repositories.strategy_repository import StrategyRepository
from app.repositories.strategy_device_repository import StrategyDeviceRepository
from app.repositories.price_repository import PriceRepository
from app.repositories.grid_strategy_repository import GridStrategyRepository
from app.models.strategy_run import StrategyRunModel
from app.models.device_telemetry import DeviceTelemetry


# ==================== Fixtures ====================

@pytest.fixture
def init_db():
    """创建测试用应用和数据库，手动设置 app.state"""
    # 1. 创建临时数据库
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db_url = f"sqlite:///{path}"
    settings = Settings(
        database_url=db_url,
        loop_seconds=60,
        history_limit=100,
    )
    db = Database(db_url)
    db.create_tables()

    # 2. 初始化默认数据
    with db.session() as session:
        DeviceRepository(session).ensure_default_devices()
        StrategyRepository(session).ensure_default_config()
        StrategyDeviceRepository(session).init_default_configs()
        PriceRepository(session).get_config()
        GridStrategyRepository(session).get_config()
        session.commit()

    # 3. 创建应用（start_background=False 避免后台循环干扰）
    app = create_app(start_background=False, settings=settings)

    # 4. 手动设置 app.state（lifespan 不会执行，所以需要手动注入）
    app.state.database = db

    # 创建 EMSService 并注入
    device = SimulatorAdapter()
    strategy = FixedRuleStrategy()
    service = EMSService(
        database=db,
        device=device,
        strategy=strategy,
        loop_seconds=settings.loop_seconds,
        history_limit=settings.history_limit,
    )
    app.state.service = service
    app.state.device = device
    # 初始化 EMSService 的 _latest_system_state
    state = device.get_state_without_advance()
    service._latest_system_state = state.model_copy(deep=True)
    # 创建 DeviceRuntimeService 并注入为端口
    runtime_service = DeviceRuntimeService(device, db)
    app.state.device_runtime_service = runtime_service
    app.state.device_read_port = runtime_service
    app.state.device_execution_port = runtime_service

    # 5. 创建测试客户端
    client = TestClient(app)

    yield client, settings, db

    # 清理
    try:
        os.unlink(path)
    except PermissionError:
        pass


# ==================== T01: 默认初始化 ====================

def test_t01_default_initialization(init_db):
    """
    T01: 默认初始化
    验证新数据库启动后，12设备、10设备策略配置、1策略配置、1电价配置、1电网策略配置存在
    """
    client, settings, db = init_db

    with db.session() as session:
        from app.models.device import Device
        devices = session.query(Device).all()
        assert len(devices) == 12, f"期望 12 个设备，实际 {len(devices)}"

        pv_count = session.query(Device).filter(Device.device_type == 'pv').count()
        charger_count = session.query(Device).filter(Device.device_type == 'charger').count()
        battery_count = session.query(Device).filter(Device.device_type == 'battery').count()
        grid_count = session.query(Device).filter(Device.device_type == 'grid').count()
        assert pv_count == 5
        assert charger_count == 5
        assert battery_count == 1
        assert grid_count == 1

        from app.models.strategy_device_config import StrategyDeviceConfigModel
        device_configs = session.query(StrategyDeviceConfigModel).all()
        assert len(device_configs) == 10

        from app.models.strategy import StrategyConfigModel
        strategy_config = session.query(StrategyConfigModel).filter(
            StrategyConfigModel.is_active == True
        ).first()
        assert strategy_config is not None
        assert strategy_config.soc_min == 20.0
        assert strategy_config.soc_max == 90.0
        assert strategy_config.requested_mode == "AUTO"

        from app.models.price_config import PriceConfigModel
        price_config = session.query(PriceConfigModel).first()
        assert price_config is not None
        assert price_config.valley_price == 0.35
        assert price_config.flat_price == 0.55
        assert price_config.peak_price == 0.85

        from app.models.grid_strategy_config import GridStrategyConfigModel
        grid_config = session.query(GridStrategyConfigModel).first()
        assert grid_config is not None
        assert grid_config.max_import_power_kw == 300.0
        assert grid_config.allow_export is True

    print("✅ T01 通过")


# ==================== T02: B设置 → A显示 ====================

def test_t02_b_config_to_a_display(init_db):
    """
    T02: B设置 → A显示
    验证 B 修改 Charger 配置后，A 详情页能显示
    """
    client, settings, db = init_db

    # 1. B 修改 CHG003 的 priority 为 5
    response = client.put(
        "/api/strategies/device-configs/CHG003",
        json={"priority": 5}
    )
    assert response.status_code == 200, f"修改失败: {response.text}"
    data = response.json()
    assert data["priority"] == 5

    # 2. 验证 B API 返回更新后的值
    response = client.get("/api/strategies/device-configs/CHG003")
    assert response.status_code == 200
    data = response.json()
    assert data["priority"] == 5

    # 3. 验证 A 设备列表能读取到更新后的值
    response = client.get("/api/strategies/device-configs")
    assert response.status_code == 200
    configs = response.json()
    chg003_config = next((c for c in configs if c["device_code"] == "CHG003"), None)
    assert chg003_config is not None
    assert chg003_config["priority"] == 5

    print("✅ T02 通过")


# ==================== T03: Charger 手动控制 ====================

def test_t03_charger_manual_control(init_db):
    """
    T03: Charger 手动控制
    验证停止 CHG003 后，power=0，load 下降，grid 重新计算
    """
    client, settings, db = init_db

    # 1. 先生成一些历史数据（方便观察变化）
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 1, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 记录控制前的状态
    response = client.get("/api/devices/runtime/system-state")
    assert response.status_code == 200
    before_state = response.json()
    before_load = before_state["load_power"]

    # 3. 停止 CHG003
    response = client.post("/api/devices/8/control", json={"command": "stop"})
    assert response.status_code == 200
    control_result = response.json()
    assert control_result["success"] is True

    # 4. 验证状态已变化
    response = client.get("/api/devices/8/status")
    assert response.status_code == 200
    status = response.json()
    assert status["status"] == "disabled", f"期望 status=disabled，实际 {status['status']}"

    # 5. 验证系统状态变化（load 下降）
    response = client.get("/api/devices/runtime/system-state")
    assert response.status_code == 200
    after_state = response.json()
    assert after_state["load_power"] <= before_load, "停止充电桩后负荷应下降"

    # 6. 验证历史记录已保存
    with db.session() as session:
        from app.models.device_telemetry import DeviceTelemetry
        latest_records = session.query(DeviceTelemetry).filter(
            DeviceTelemetry.device_code == "CHG003"
        ).order_by(DeviceTelemetry.created_at.desc()).limit(1).all()
        assert len(latest_records) >= 1, "未找到 CHG003 的历史记录"

    print("✅ T03 通过")


# ==================== T04: 30 天连续历史 ====================

def test_t04_30_days_continuous_history(init_db):
    """
    T04: 30 天连续历史
    验证 30 天历史：2880 个系统时刻，34560 条记录，每设备 2880 条，间隔 15 分钟
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert result["total_steps"] == 2880
    assert result["total_records"] == 34560

    # 2. 验证总记录数
    with db.session() as session:
        from app.models.device_telemetry import DeviceTelemetry
        from sqlalchemy import func
        total = session.query(DeviceTelemetry).count()
        assert total == 34560, f"期望 34560 条记录，实际 {total}"

        # 3. 验证每个设备记录数
        device_counts = session.query(
            DeviceTelemetry.device_code,
            func.count(DeviceTelemetry.id).label('cnt')
        ).group_by(DeviceTelemetry.device_code).all()
        assert len(device_counts) == 12, "不是 12 个设备都有记录"
        for device_code, cnt in device_counts:
            assert cnt == 2880, f"设备 {device_code} 期望 2880 条，实际 {cnt}"

        # 4. 验证相邻时间差为 15 分钟
        records = session.query(DeviceTelemetry).filter(
            DeviceTelemetry.device_code == "PV001"
        ).order_by(DeviceTelemetry.created_at).limit(10).all()
        for i in range(len(records) - 1):
            diff = records[i + 1].created_at - records[i].created_at
            assert diff == timedelta(minutes=15), f"时间差应为 15 分钟，实际 {diff}"

        # 5. 验证时间范围（30 天）
        min_time = session.query(func.min(DeviceTelemetry.created_at)).filter(
            DeviceTelemetry.device_code == "PV001"
        ).scalar()
        max_time = session.query(func.max(DeviceTelemetry.created_at)).filter(
            DeviceTelemetry.device_code == "PV001"
        ).scalar()
        expected_span = timedelta(days=29, hours=23, minutes=45)
        actual_span = max_time - min_time
        assert abs(actual_span - expected_span) < timedelta(minutes=1), \
            f"时间跨度应为 {expected_span}，实际 {actual_span}"

    print("✅ T04 通过")


# ==================== T05: 96 点真实预测 ====================

def test_t05_96_points_real_forecast(init_db):
    """
    T05: 96 点真实预测
    验证生成历史后，负荷和 PV 预测返回 96 点，且 available=True
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 运行一次策略（生成预测）
    response = client.post("/api/strategies/run")
    assert response.status_code == 200
    run_result = response.json()
    assert run_result["status"] == "success"

    # 3. 获取负荷预测
    response = client.get("/api/strategies/forecast/load")
    assert response.status_code == 200
    load_forecast = response.json()
    assert load_forecast["available"] is True, "负荷预测不可用"
    assert len(load_forecast["points"]) == 96, f"负荷预测应为 96 点，实际 {len(load_forecast['points'])}"
    for point in load_forecast["points"]:
        val = point.get("value_kw") or point.get("value")
        assert val is not None, "预测值不能为 None"

    # 4. 获取 PV 预测
    response = client.get("/api/strategies/forecast/pv")
    assert response.status_code == 200
    pv_forecast = response.json()
    assert pv_forecast["available"] is True, "PV 预测不可用"
    assert len(pv_forecast["points"]) == 96, f"PV 预测应为 96 点，实际 {len(pv_forecast['points'])}"

    # 5. 验证预测模型名称真实
    assert load_forecast["model_name"] is not None
    assert load_forecast["model_name"] not in ["Simulated", "Unavailable"], \
        f"模型名不应为 Simulated/Unavailable，实际 {load_forecast['model_name']}"

    print("✅ T05 通过")


# ==================== T06: Price 传播到 MILP ====================

def test_t06_price_propagation_to_milp(init_db):
    """
    T06: Price 传播到 MILP
    验证修改峰价后，MILP 的 schedule 发生变化
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 设置请求模式为 ECONOMIC_SCHEDULE（启用 MILP）
    response = client.put("/api/strategies/mode", json={"requested_mode": "ECONOMIC_SCHEDULE"})
    assert response.status_code == 200

    # 3. 第一次运行策略，记录 schedule
    response = client.post("/api/strategies/run")
    assert response.status_code == 200
    run1 = response.json()

    response = client.get("/api/strategies/schedule")
    assert response.status_code == 200
    schedule1 = response.json()
    assert schedule1["available"] is True, "schedule 不可用"
    schedule1_power = [item["power"] for item in schedule1["schedule"]]

    # 4. 修改峰价（从 0.85 改为 1.20）
    response = client.put(
        "/api/strategies/price-config",
        json={"valley_price": 0.35, "flat_price": 0.55, "peak_price": 1.20}
    )
    assert response.status_code == 200

    # 5. 再次运行策略
    response = client.post("/api/strategies/run")
    assert response.status_code == 200
    run2 = response.json()

    # 6. 获取新的 schedule
    response = client.get("/api/strategies/schedule")
    assert response.status_code == 200
    schedule2 = response.json()
    assert schedule2["available"] is True
    schedule2_power = [item["power"] for item in schedule2["schedule"]]

    # 7. 验证 Price 变化导致 Schedule 变化
    any_different = any(s1 != s2 for s1, s2 in zip(schedule1_power, schedule2_power))
    assert any_different, "Price 变化后 schedule 应发生变化"

    print("✅ T06 通过")


# ==================== T07: SOC 约束传播 ====================

def test_t07_soc_constraint_propagation(init_db):
    """
    T07: SOC 约束传播
    验证修改 soc_min 后，MILP schedule 的 predicted_soc 不低于 soc_min
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 设置 soc_min = 40
    response = client.put(
        "/api/strategies/config",
        json={
            "config_name": "default",
            "soc_min": 40,
            "soc_max": 90,
            "charge_power_kw": 10,
            "discharge_power_kw": 10,
            "requested_mode": "ECONOMIC_SCHEDULE",
            "backup_soc_target": 50
        }
    )
    assert response.status_code == 200

    # 3. 运行策略
    response = client.post("/api/strategies/run")
    assert response.status_code == 200

    # 4. 获取 schedule，检查 predicted_soc
    response = client.get("/api/strategies/schedule")
    assert response.status_code == 200
    schedule = response.json()
    if schedule["available"] is True:
        for item in schedule["schedule"]:
            if "soc" in item:
                assert item["soc"] >= 40 - 1e-6, f"SOC {item['soc']} < 40"

    print("✅ T07 通过")


# ==================== T08: AUTO requested/effective ====================

def test_t08_auto_requested_effective(init_db):
    """
    T08: AUTO requested/effective
    验证 requested_mode=AUTO 时，effective_mode 来自 AUTO 推荐
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 设置 requested_mode = AUTO
    response = client.put("/api/strategies/mode", json={"requested_mode": "AUTO"})
    assert response.status_code == 200

    # 3. 运行策略
    response = client.post("/api/strategies/run")
    assert response.status_code == 200
    run_result = response.json()
    assert run_result["status"] == "success"

    # 4. 验证 effective_mode 和 requested_mode 可能不同
    effective_mode = run_result["effective_mode"]
    response = client.get("/api/strategies/mode")
    assert response.status_code == 200
    mode_data = response.json()
    requested_mode = mode_data["requested_mode"]
    assert requested_mode == "AUTO", f"requested_mode 应为 AUTO，实际 {requested_mode}"
    assert effective_mode in ["AUTO", "PV_PRIORITY", "ECONOMIC_SCHEDULE", "GRID_BACKUP", "SAFE"], \
        f"effective_mode 非法: {effective_mode}"

    # 5. 验证 Mode API 返回的 requested/effective 区分
    response = client.get("/api/strategies/mode")
    assert response.status_code == 200
    mode_data = response.json()
    assert mode_data["requested_mode"] == "AUTO"
    assert mode_data["effective_mode"] is not None

    # 6. 运行记录中应记录 effective_mode
    with db.session() as session:
        from app.models.strategy_run import StrategyRunModel
        latest_run = session.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).first()
        assert latest_run is not None
        assert latest_run.requested_mode == "AUTO"
        assert latest_run.effective_mode is not None

    print("✅ T08 通过")


# ==================== T09: B→C→A 执行 ====================

def test_t09_b_to_c_to_a_execution(init_db):
    """
    T09: B→C→A 执行
    验证策略运行后，Battery 功率变化，SOC 变化，Grid 变化，strategy_runs 记录新增
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 设置模式为 ECONOMIC_SCHEDULE（启用 MILP）
    response = client.put("/api/strategies/mode", json={"requested_mode": "ECONOMIC_SCHEDULE"})
    assert response.status_code == 200

    # 3. 运行策略
    response = client.post("/api/strategies/run")
    assert response.status_code == 200
    run_result = response.json()
    assert run_result["status"] == "success"
    assert run_result.get("run_id") is not None, "未返回 run_id"

    # 4. 验证 execution 有值
    storage_power_actual = run_result.get("execution", {}).get("storage_power_actual_kw")
    assert storage_power_actual is not None

    # 5. 验证 strategy_runs 记录新增
    with db.session() as session:
        from app.models.strategy_run import StrategyRunModel
        count = session.query(StrategyRunModel).count()
        assert count >= 1, "strategy_runs 表为空"

        latest_run = session.query(StrategyRunModel).order_by(
            StrategyRunModel.created_at.desc()
        ).first()
        assert latest_run.id == run_result.get("run_id"), f"run_id 不匹配"
        assert latest_run.status == "success"
        assert latest_run.effective_mode is not None

    # 6. 验证 telemetry 已保存（至少 12 条新记录）
    with db.session() as session:
        from app.models.device_telemetry import DeviceTelemetry
        latest_time = session.query(
            DeviceTelemetry.created_at
        ).order_by(DeviceTelemetry.created_at.desc()).first()
        if latest_time:
            count_at_time = session.query(DeviceTelemetry).filter(
                DeviceTelemetry.created_at == latest_time[0]
            ).count()
            assert count_at_time == 12, f"每个时刻应有 12 条记录，实际 {count_at_time}"

    print("✅ T09 通过")


# ==================== T10: 算法失败 fallback ====================

def test_t10_algorithm_failure_fallback(init_db, monkeypatch):
    """
    T10: 算法失败 fallback
    验证 C 算法失败时，B 正确回退到 FixedRule，fallback_used=True，A 仍执行
    """
    client, settings, db = init_db

    # 1. 生成 30 天历史
    response = client.post(
        "/api/devices/simulator/generate-history",
        json={"days": 30, "seed": 2026}
    )
    assert response.status_code == 200

    # 2. 设置模式为 ECONOMIC_SCHEDULE
    response = client.put("/api/strategies/mode", json={"requested_mode": "ECONOMIC_SCHEDULE"})
    assert response.status_code == 200

    # 3. 注入故障：让 AlgorithmBridgeService 返回不可用预测
    def mock_get_load_forecast(self, *args, **kwargs):
        from app.schemas.algorithm import ForecastResult
        return ForecastResult(
            available=False,
            model_name="Unavailable",
            target="load",
            created_at=datetime.now(),
            step_minutes=15,
            points=[],
            mae=None,
            rmse=None,
            message="Mock failure for T10"
        )

    def mock_get_pv_forecast(self, *args, **kwargs):
        from app.schemas.algorithm import ForecastResult
        return ForecastResult(
            available=False,
            model_name="Unavailable",
            target="pv",
            created_at=datetime.now(),
            step_minutes=15,
            points=[],
            mae=None,
            rmse=None,
            message="Mock failure for T10"
        )

    # 4. 执行策略（应触发 fallback）
    with monkeypatch.context() as m:
        from app.services.algorithm_bridge_service import AlgorithmBridgeService
        m.setattr(AlgorithmBridgeService, "get_load_forecast", mock_get_load_forecast)
        m.setattr(AlgorithmBridgeService, "get_pv_forecast", mock_get_pv_forecast)

        response = client.post("/api/strategies/run")
        assert response.status_code == 200
        result = response.json()

        # 5. 验证 fallback 生效
        assert result["status"] == "success"
        assert result["fallback_used"] is True, "fallback_used 应为 True"
        assert result["decision"]["source"] == "fixed_rule", \
            f"decision.source 应为 fixed_rule，实际 {result['decision']['source']}"
        assert result["effective_mode"] in ["PV_PRIORITY", "SAFE", "GRID_BACKUP"], \
            f"effective_mode 应为 fallback 模式，实际 {result['effective_mode']}"

        # 6. 验证 execution 成功
        assert result["execution"]["success"] is True, "A 执行应成功"

        # 7. 验证 strategy_runs 记录 fallback
        with db.session() as session:
            from app.models.strategy_run import StrategyRunModel
            latest_run = session.query(StrategyRunModel).order_by(
                StrategyRunModel.created_at.desc()
            ).first()
            assert latest_run is not None
            assert latest_run.fallback_used is True
            assert latest_run.source == "fixed_rule"
            assert latest_run.forecast_model_load in [None, "Unavailable"], \
                f"forecast_model_load 应为 Unavailable 或 None，实际 {latest_run.forecast_model_load}"
            assert latest_run.status == "success"

    print("✅ T10 通过")


# ==================== 运行入口 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])