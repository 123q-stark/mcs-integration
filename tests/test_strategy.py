# tests/test_strategy.py
"""
策略模块测试
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.strategy import StrategyConfigModel


@pytest.fixture
def db_session():
    """创建临时测试数据库"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_strategy_config(db_session):
    """测试正常创建策略配置"""
    config = StrategyConfigModel(
        config_name="test_config",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )
    db_session.add(config)
    db_session.commit()

    saved = db_session.query(StrategyConfigModel).filter_by(config_name="test_config").first()
    assert saved is not None
    assert saved.soc_min == 20.0
    assert saved.soc_max == 90.0
    assert saved.charge_power_kw == 10.0
    assert saved.discharge_power_kw == 10.0
    assert saved.is_active is True


def test_config_name_unique(db_session):
    """测试 config_name 唯一约束"""
    config1 = StrategyConfigModel(
        config_name="unique_test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
    )
    db_session.add(config1)
    db_session.commit()

    config2 = StrategyConfigModel(
        config_name="unique_test",  # 相同名称
        soc_min=30.0,
        soc_max=80.0,
        charge_power_kw=5.0,
        discharge_power_kw=5.0,
    )
    db_session.add(config2)
    with pytest.raises(Exception):  # 应该抛出唯一约束异常
        db_session.commit()


def test_required_fields(db_session):
    """测试必填字段缺失"""
    # 缺少 config_name
    with pytest.raises(Exception):
        config = StrategyConfigModel(
            soc_min=20.0,
            soc_max=90.0,
            charge_power_kw=10.0,
            discharge_power_kw=10.0,
        )
        db_session.add(config)
        db_session.commit()


# ============ B-02: Schema 测试 ============

from app.schemas.strategy import StrategyConfigUpdate, StrategyPreviewRequest


def test_strategy_config_update_valid():
    """测试合法配置更新"""
    data = {
        "config_name": "test",
        "soc_min": 20.0,
        "soc_max": 90.0,
        "charge_power_kw": 10.0,
        "discharge_power_kw": 10.0,
        "is_active": True,
    }
    config = StrategyConfigUpdate(**data)
    assert config.soc_min == 20.0
    assert config.soc_max == 90.0


def test_strategy_config_update_soc_equal():
    """测试 soc_min == soc_max 失败"""
    data = {
        "config_name": "test",
        "soc_min": 50.0,
        "soc_max": 50.0,
        "charge_power_kw": 10.0,
        "discharge_power_kw": 10.0,
    }
    with pytest.raises(ValueError):
        StrategyConfigUpdate(**data)


def test_strategy_config_update_soc_min_greater():
    """测试 soc_min > soc_max 失败"""
    data = {
        "config_name": "test",
        "soc_min": 90.0,
        "soc_max": 80.0,
        "charge_power_kw": 10.0,
        "discharge_power_kw": 10.0,
    }
    with pytest.raises(ValueError):
        StrategyConfigUpdate(**data)


def test_strategy_config_update_soc_out_of_range():
    """测试 SOC 超出 0-100 失败"""
    data = {
        "config_name": "test",
        "soc_min": -10.0,
        "soc_max": 110.0,
        "charge_power_kw": 10.0,
        "discharge_power_kw": 10.0,
    }
    with pytest.raises(ValueError):
        StrategyConfigUpdate(**data)


def test_strategy_config_update_power_zero():
    """测试功率 <= 0 失败"""
    data = {
        "config_name": "test",
        "soc_min": 20.0,
        "soc_max": 90.0,
        "charge_power_kw": 0.0,
        "discharge_power_kw": 10.0,
    }
    with pytest.raises(ValueError):
        StrategyConfigUpdate(**data)


def test_preview_request_valid():
    """测试预览请求合法"""
    data = {
        "pv_power": 40.0,
        "load_power": 70.0,
        "storage_power": 0.0,
        "storage_soc": 60.0,
    }
    request = StrategyPreviewRequest(**data)
    assert request.pv_power == 40.0
    assert request.load_power == 70.0
    assert request.storage_soc == 60.0


def test_preview_request_soc_out_of_range():
    """测试预览请求 SOC 超出范围"""
    data = {
        "pv_power": 40.0,
        "load_power": 70.0,
        "storage_power": 0.0,
        "storage_soc": 150.0,
    }
    with pytest.raises(ValueError):
        StrategyPreviewRequest(**data)


# ============ B-03: Repository 测试 ============

from app.repositories.strategy_repository import StrategyRepository


def test_repository_ensure_default_config(db_session):
    """测试幂等初始化默认配置"""
    repo = StrategyRepository(db_session)

    # 第一次初始化应该创建
    config1 = repo.ensure_default_config()
    assert config1 is not None
    assert config1.config_name == "default"
    assert config1.soc_min == 20.0
    assert config1.soc_max == 90.0
    assert config1.charge_power_kw == 10.0
    assert config1.discharge_power_kw == 10.0
    assert config1.is_active is True

    # 第二次初始化应该返回已有配置（不重复创建）
    config2 = repo.ensure_default_config()
    assert config2.id == config1.id
    assert db_session.query(StrategyConfigModel).count() == 1


def test_repository_get_active_config(db_session):
    """测试获取活动配置"""
    repo = StrategyRepository(db_session)

    # 先创建默认配置
    repo.ensure_default_config()

    active = repo.get_active_config()
    assert active is not None
    assert active.is_active is True


def test_repository_update_active_config(db_session):
    """测试更新活动配置"""
    repo = StrategyRepository(db_session)
    repo.ensure_default_config()

    # 更新配置
    new_config = repo.update_active_config(
        config_name="new_config",
        soc_min=30.0,
        soc_max=80.0,
        charge_power_kw=8.0,
        discharge_power_kw=8.0,
    )

    assert new_config.config_name == "new_config"
    assert new_config.soc_min == 30.0
    assert new_config.soc_max == 80.0
    assert new_config.charge_power_kw == 8.0
    assert new_config.discharge_power_kw == 8.0

    # 验证旧的被停用，新的被激活
    all_configs = db_session.query(StrategyConfigModel).all()
    active_configs = [c for c in all_configs if c.is_active]
    assert len(active_configs) == 1
    assert active_configs[0].config_name == "new_config"


def test_repository_get_by_name(db_session):
    """测试按名称查询"""
    repo = StrategyRepository(db_session)
    repo.ensure_default_config()

    found = repo.get_by_name("default")
    assert found is not None
    assert found.config_name == "default"

    not_found = repo.get_by_name("nonexistent")
    assert not_found is None


def test_repository_get_by_id(db_session):
    """测试按 ID 查询"""
    repo = StrategyRepository(db_session)
    config = repo.ensure_default_config()

    found = repo.get_by_id(config.id)
    assert found is not None
    assert found.id == config.id

    not_found = repo.get_by_id(999)
    assert not_found is None


# ============ B-04: 策略参数化测试 ============

from app.strategies.fixed_rule import FixedRuleStrategy
from app.schemas import SystemState
from app.schemas.strategy import StrategyConfigUpdate
from datetime import datetime


def test_strategy_charge_scenario():
    """测试充电场景：光伏充足，SOC 未满"""
    strategy = FixedRuleStrategy()
    state = SystemState(
        timestamp=datetime.now(),
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=50.0,
        simulated_hour=12.0,
    )

    config = StrategyConfigUpdate(
        config_name="test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )

    decision = strategy.calculate(state, config)
    assert decision.action == "charge"
    assert decision.storage_power_target == -10.0
    assert "充电" in decision.message


def test_strategy_discharge_scenario():
    """测试放电场景：光伏不足，SOC 高于下限"""
    strategy = FixedRuleStrategy()
    state = SystemState(
        timestamp=datetime.now(),
        pv_power=20.0,
        load_power=50.0,
        storage_power=0.0,
        storage_soc=60.0,
        simulated_hour=12.0,
    )

    config = StrategyConfigUpdate(
        config_name="test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )

    decision = strategy.calculate(state, config)
    assert decision.action == "discharge"
    assert decision.storage_power_target == 10.0
    assert "放电" in decision.message


def test_strategy_charge_soc_high_idle():
    """测试 SOC 达到上限时停止充电"""
    strategy = FixedRuleStrategy()
    state = SystemState(
        timestamp=datetime.now(),
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=95.0,
        simulated_hour=12.0,
    )

    config = StrategyConfigUpdate(
        config_name="test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )

    decision = strategy.calculate(state, config)
    assert decision.action == "idle"
    assert decision.storage_power_target == 0.0
    assert "上限" in decision.message


def test_strategy_discharge_soc_low_idle():
    """测试 SOC 达到下限时停止放电"""
    strategy = FixedRuleStrategy()
    state = SystemState(
        timestamp=datetime.now(),
        pv_power=20.0,
        load_power=50.0,
        storage_power=0.0,
        storage_soc=10.0,
        simulated_hour=12.0,
    )

    config = StrategyConfigUpdate(
        config_name="test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )

    decision = strategy.calculate(state, config)
    assert decision.action == "idle"
    assert decision.storage_power_target == 0.0
    assert "下限" in decision.message


def test_strategy_with_custom_config():
    """测试自定义配置（非默认值）"""
    strategy = FixedRuleStrategy()
    state = SystemState(
        timestamp=datetime.now(),
        pv_power=30.0,
        load_power=10.0,
        storage_power=0.0,
        storage_soc=50.0,
        simulated_hour=12.0,
    )

    config = StrategyConfigUpdate(
        config_name="custom",
        soc_min=30.0,
        soc_max=80.0,
        charge_power_kw=5.0,
        discharge_power_kw=5.0,
        is_active=True,
    )

    decision = strategy.calculate(state, config)
    assert decision.action == "charge"
    assert decision.storage_power_target == -5.0
    assert "5.0" in decision.message


def test_strategy_power_direction():
    """测试功率方向：充电为负，放电为正，待机为 0"""
    strategy = FixedRuleStrategy()
    config = StrategyConfigUpdate(
        config_name="test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )

    # 充电场景
    state_charge = SystemState(
        timestamp=datetime.now(),
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=50.0,
        simulated_hour=12.0,
    )
    decision_charge = strategy.calculate(state_charge, config)
    assert decision_charge.storage_power_target < 0

    # 放电场景
    state_discharge = SystemState(
        timestamp=datetime.now(),
        pv_power=20.0,
        load_power=50.0,
        storage_power=0.0,
        storage_soc=60.0,
        simulated_hour=12.0,
    )
    decision_discharge = strategy.calculate(state_discharge, config)
    assert decision_discharge.storage_power_target > 0

    # 待机场景
    state_idle = SystemState(
        timestamp=datetime.now(),
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=95.0,
        simulated_hour=12.0,
    )
    decision_idle = strategy.calculate(state_idle, config)
    assert decision_idle.storage_power_target == 0.0


def test_strategy_without_config_fallback():
    """测试未传入配置时使用默认值（向后兼容）"""
    strategy = FixedRuleStrategy()
    state = SystemState(
        timestamp=datetime.now(),
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=50.0,
        simulated_hour=12.0,
    )

    decision = strategy.calculate(state)
    assert decision.action == "charge"
    assert decision.storage_power_target == -10.0


# ============ B-05: Service 测试 ============

from app.services.strategy_service import StrategyService
from app.schemas.strategy import StrategyConfigUpdate, StrategyPreviewRequest


def test_service_get_current_config(db_session):
    """测试获取当前配置"""
    service = StrategyService(db_session)
    # 确保默认配置已存在
    service.repository.ensure_default_config()

    config = service.get_current_config()
    assert config is not None
    assert config.config_name == "default"
    assert config.soc_min == 20.0


def test_service_update_current_config(db_session):
    """测试更新当前配置"""
    service = StrategyService(db_session)
    service.repository.ensure_default_config()

    update_data = StrategyConfigUpdate(
        config_name="updated",
        soc_min=30.0,
        soc_max=80.0,
        charge_power_kw=8.0,
        discharge_power_kw=8.0,
        is_active=True,
    )

    new_config = service.update_current_config(update_data)
    assert new_config.config_name == "updated"
    assert new_config.soc_min == 30.0
    assert new_config.soc_max == 80.0

    # 验证只有一条激活配置
    active = service.repository.get_active_config()
    assert active.config_name == "updated"


def test_service_preview_decision_charge(db_session):
    """测试预览决策：充电场景"""
    service = StrategyService(db_session)
    service.repository.ensure_default_config()

    request = StrategyPreviewRequest(
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=50.0,
    )
    response = service.preview_decision(request)

    assert response.action == "charge"
    assert response.storage_power_target == -10.0
    assert "充电" in response.message


def test_service_preview_decision_discharge(db_session):
    """测试预览决策：放电场景"""
    service = StrategyService(db_session)
    service.repository.ensure_default_config()

    request = StrategyPreviewRequest(
        pv_power=20.0,
        load_power=50.0,
        storage_power=0.0,
        storage_soc=60.0,
    )
    response = service.preview_decision(request)

    assert response.action == "discharge"
    assert response.storage_power_target == 10.0
    assert "放电" in response.message


def test_service_preview_decision_idle(db_session):
    """测试预览决策：待机场景"""
    service = StrategyService(db_session)
    service.repository.ensure_default_config()

    request = StrategyPreviewRequest(
        pv_power=50.0,
        load_power=20.0,
        storage_power=0.0,
        storage_soc=95.0,
    )
    response = service.preview_decision(request)

    assert response.action == "idle"
    assert response.storage_power_target == 0.0
    assert "上限" in response.message


def test_service_preview_uses_active_config(db_session):
    """测试预览使用当前激活的配置（而非默认）"""
    service = StrategyService(db_session)
    service.repository.ensure_default_config()

    # 更新配置为自定义值
    update_data = StrategyConfigUpdate(
        config_name="custom",
        soc_min=30.0,
        soc_max=80.0,
        charge_power_kw=5.0,
        discharge_power_kw=5.0,
        is_active=True,
    )
    service.update_current_config(update_data)

    # 预览应该使用新配置
    request = StrategyPreviewRequest(
        pv_power=30.0,
        load_power=10.0,
        storage_power=0.0,
        storage_soc=50.0,
    )
    response = service.preview_decision(request)

    assert response.storage_power_target == -5.0  # 使用 5kW 充电
    assert "5.0" in response.message


# ============ B-06: API 测试 ============

from fastapi.testclient import TestClient
from app.main import create_app


def test_api_get_config(db_session):
    """测试 GET /api/strategies/config"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database
    from app.repositories.strategy_repository import StrategyRepository

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        # ===== 关键修复：手动将 database 注入 app.state =====
        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        # 确保默认配置存在
        with db.session() as session:
            repo = StrategyRepository(session)
            repo.ensure_default_config()

        client = TestClient(app)

        response = client.get("/api/strategies/config")
        assert response.status_code == 200
        data = response.json()
        assert data["config_name"] == "default"
        assert data["soc_min"] == 20.0
        assert data["soc_max"] == 90.0
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_api_update_config():
    """测试 PUT /api/strategies/config"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database
    from app.repositories.strategy_repository import StrategyRepository

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        # ===== 关键修复：手动将 database 注入 app.state =====
        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        # 确保默认配置存在
        with db.session() as session:
            repo = StrategyRepository(session)
            repo.ensure_default_config()

        client = TestClient(app)

        update_data = {
            "config_name": "api_test",
            "soc_min": 30.0,
            "soc_max": 80.0,
            "charge_power_kw": 8.0,
            "discharge_power_kw": 8.0,
            "is_active": True,
        }
        response = client.put("/api/strategies/config", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["config_name"] == "api_test"
        assert data["soc_min"] == 30.0
        assert data["soc_max"] == 80.0

        # 验证 GET 返回更新后的值
        response = client.get("/api/strategies/config")
        assert response.status_code == 200
        data = response.json()
        assert data["config_name"] == "api_test"
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_api_update_config_invalid():
    """测试 PUT 传入非法参数（SOC 超出范围）"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        client = TestClient(app)

        update_data = {
            "config_name": "invalid",
            "soc_min": 90.0,
            "soc_max": 80.0,
            "charge_power_kw": 10.0,
            "discharge_power_kw": 10.0,
            "is_active": True,
        }
        response = client.put("/api/strategies/config", json=update_data)
        assert response.status_code == 422
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


# ============ B-07: 预览 API 测试 ============

def test_api_preview_charge():
    """测试预览 API：充电场景"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database
    from app.repositories.strategy_repository import StrategyRepository

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        with db.session() as session:
            repo = StrategyRepository(session)
            repo.ensure_default_config()

        client = TestClient(app)

        preview_data = {
            "pv_power": 50.0,
            "load_power": 20.0,
            "storage_power": 0.0,
            "storage_soc": 50.0,
        }
        response = client.post("/api/strategies/preview", json=preview_data)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "charge"
        assert data["storage_power_target"] == -10.0
        assert "充电" in data["message"]
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_api_preview_discharge():
    """测试预览 API：放电场景"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database
    from app.repositories.strategy_repository import StrategyRepository

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        with db.session() as session:
            repo = StrategyRepository(session)
            repo.ensure_default_config()

        client = TestClient(app)

        preview_data = {
            "pv_power": 20.0,
            "load_power": 50.0,
            "storage_power": 0.0,
            "storage_soc": 60.0,
        }
        response = client.post("/api/strategies/preview", json=preview_data)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "discharge"
        assert data["storage_power_target"] == 10.0
        assert "放电" in data["message"]
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_api_preview_idle():
    """测试预览 API：待机场景（SOC 过高）"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database
    from app.repositories.strategy_repository import StrategyRepository

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        with db.session() as session:
            repo = StrategyRepository(session)
            repo.ensure_default_config()

        client = TestClient(app)

        preview_data = {
            "pv_power": 50.0,
            "load_power": 20.0,
            "storage_power": 0.0,
            "storage_soc": 95.0,
        }
        response = client.post("/api/strategies/preview", json=preview_data)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "idle"
        assert data["storage_power_target"] == 0.0
        assert "上限" in data["message"]
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_api_preview_invalid_soc():
    """测试预览 API：传入非法 SOC（超出范围）"""
    import tempfile
    import os
    from app.config import Settings
    from app.database import Database

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        db = Database(settings.database_url)
        db.create_tables()
        app.state.database = db

        client = TestClient(app)

        preview_data = {
            "pv_power": 50.0,
            "load_power": 20.0,
            "storage_power": 0.0,
            "storage_soc": 150.0,
        }
        response = client.post("/api/strategies/preview", json=preview_data)
        assert response.status_code == 422
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


# ============ B-08: 页面测试 ============

def test_strategy_page():
    """测试策略配置页面是否可访问"""
    import tempfile
    import os
    from app.config import Settings

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)
        client = TestClient(app)

        response = client.get("/strategy")
        assert response.status_code == 200
        # 检查页面关键内容
        assert "策略配置" in response.text
        assert "SOC 下限" in response.text or "SOC下限" in response.text
        assert "预览" in response.text
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass
# ==================== B-RC2-01: 策略重复保存测试 ====================

def test_update_active_config_idempotent(db_session):
    """测试同名配置连续更新两次都成功"""
    repo = StrategyRepository(db_session)

    # 清空所有配置
    db_session.query(StrategyConfigModel).delete()
    db_session.commit()

    # 第一次保存
    config1 = repo.update_active_config(
        config_name="default",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=True,
    )
    assert config1.id is not None

    # 第二次保存（同名，不同参数）
    config2 = repo.update_active_config(
        config_name="default",
        soc_min=25.0,
        soc_max=85.0,
        charge_power_kw=8.0,
        discharge_power_kw=8.0,
        is_active=True,
    )

    # 验证只有一条记录
    all_configs = db_session.query(StrategyConfigModel).all()
    assert len(all_configs) == 1

    # 验证更新生效
    assert config2.soc_min == 25.0
    assert config2.soc_max == 85.0
    assert config2.charge_power_kw == 8.0
    assert config2.discharge_power_kw == 8.0


def test_update_active_config_no_active_but_exists(db_session):
    """测试无激活配置但有同名配置时，更新并激活"""
    repo = StrategyRepository(db_session)

    # 清空并创建一条非激活配置
    db_session.query(StrategyConfigModel).delete()
    db_session.commit()

    existing = StrategyConfigModel(
        config_name="old_default",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
        is_active=False,
    )
    db_session.add(existing)
    db_session.commit()

    # 更新时传入同名
    config = repo.update_active_config(
        config_name="old_default",
        soc_min=30.0,
        soc_max=80.0,
        charge_power_kw=12.0,
        discharge_power_kw=12.0,
        is_active=True,
    )

    # 验证：同一个对象被更新
    assert config.id == existing.id
    assert config.soc_min == 30.0
    assert config.is_active is True


# ==================== B-RC2-02: 策略功率限制测试 ====================

def test_strategy_power_limit_schema():
    """测试功率字段在 Schema 中被限制为 <= 10"""
    from app.schemas.strategy import StrategyConfigUpdate

    # 10 合法
    valid = StrategyConfigUpdate(
        config_name="test",
        soc_min=20.0,
        soc_max=90.0,
        charge_power_kw=10.0,
        discharge_power_kw=10.0,
    )
    assert valid.charge_power_kw == 10.0

    # 10.1 非法
    with pytest.raises(ValueError):
        StrategyConfigUpdate(
            config_name="test",
            soc_min=20.0,
            soc_max=90.0,
            charge_power_kw=10.1,
            discharge_power_kw=10.0,
        )

    # 0 非法
    with pytest.raises(ValueError):
        StrategyConfigUpdate(
            config_name="test",
            soc_min=20.0,
            soc_max=90.0,
            charge_power_kw=0.0,
            discharge_power_kw=10.0,
        )


# ==================== B-RC2-03: 错误信息泄露测试 ====================

def test_strategy_api_error_hides_sql_details(tmp_path):
    """测试错误响应不包含 SQL 信息"""
    from app.main import create_app
    from app.config import Settings
    from fastapi.testclient import TestClient
    from app.database import Database

    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        loop_seconds=60,
        history_limit=10,
    )
    app = create_app(start_background=False, settings=settings)

    db = Database(settings.database_url)
    db.create_tables()
    app.state.database = db

    client = TestClient(app)

    # 发送超限功率数据（触发 422）
    response = client.put("/api/strategies/config", json={
        "config_name": "test",
        "soc_min": 20.0,
        "soc_max": 90.0,
        "charge_power_kw": 10.1,
        "discharge_power_kw": 10.0,
        "is_active": True,
    })

    # 422 是 Pydantic 校验错误，不包含 SQL 信息
    detail = response.text.lower()
    assert "sqlite" not in detail
    assert "sqlalchemy" not in detail