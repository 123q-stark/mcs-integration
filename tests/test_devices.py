import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from app.models.device import Device
from app.database import Base


@pytest.fixture
def db_session():
    # 显式导入 Device，确保它注册到 Base.metadata
    from app.models.device import Device  # 这行是关键
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_device(db_session):
    device = Device(
        device_code="PV001",
        device_name="模拟光伏",
        device_type="pv",
        is_online=True,
        rated_power_kw=50.0
    )
    db_session.add(device)
    db_session.commit()

    result = db_session.query(Device).filter_by(device_code="PV001").first()
    assert result is not None
    assert result.device_name == "模拟光伏"
    assert result.device_type == "pv"
    assert result.rated_power_kw == 50.0
    assert isinstance(result.created_at, datetime)


def test_unique_device_code(db_session):
    d1 = Device(device_code="ESS001", device_name="储能1", device_type="storage")
    db_session.add(d1)
    db_session.commit()

    d2 = Device(device_code="ESS001", device_name="储能2", device_type="storage")
    db_session.add(d2)
    with pytest.raises(Exception):
        db_session.commit()


def test_required_fields(db_session):
    with pytest.raises(Exception):
        device = Device(device_name="测试", device_type="pv")
        db_session.add(device)
        db_session.commit()


def test_is_online_default(db_session):
    device = Device(device_code="CHG001", device_name="充电桩", device_type="charger")
    db_session.add(device)
    db_session.commit()
    result = db_session.query(Device).filter_by(device_code="CHG001").first()
    assert result.is_online is True


def test_rated_power_nullable(db_session):
    device = Device(device_code="NULLPWR", device_name="无功率设备", device_type="pv", rated_power_kw=None)
    db_session.add(device)
    db_session.commit()
    result = db_session.query(Device).filter_by(device_code="NULLPWR").first()
    assert result.rated_power_kw is None
# ==================== A-02: Schema 测试 ====================

from datetime import datetime
from app.schemas.device import DeviceSummary, DeviceDetail, DeviceStatusResponse


def test_device_summary_schema():
    """测试 DeviceSummary 正常创建"""
    data = {
        "id": 1,
        "device_code": "PV001",
        "device_name": "模拟光伏",
        "device_type": "pv",
        "is_online": True,
        "rated_power_kw": 50.0,
        "updated_at": datetime.now(),
    }
    summary = DeviceSummary(**data)
    assert summary.id == 1
    assert summary.device_code == "PV001"
    assert summary.device_name == "模拟光伏"


def test_device_detail_schema():
    """测试 DeviceDetail 正常创建"""
    data = {
        "id": 1,
        "device_code": "PV001",
        "device_name": "模拟光伏",
        "device_type": "pv",
        "is_online": True,
        "rated_power_kw": 50.0,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    detail = DeviceDetail(**data)
    assert detail.id == 1
    assert detail.device_code == "PV001"


def test_device_status_response_schema():
    """测试 DeviceStatusResponse 正常创建（非储能设备）"""
    data = {
        "device_id": 1,
        "device_code": "PV001",
        "device_type": "pv",
        "is_online": True,
        "power_kw": 45.6,
        "storage_soc": None,
        "updated_at": datetime.now(),
    }
    status = DeviceStatusResponse(**data)
    assert status.power_kw == 45.6
    assert status.storage_soc is None


def test_device_status_response_with_soc():
    """测试 DeviceStatusResponse 正常创建（储能设备）"""
    data = {
        "device_id": 2,
        "device_code": "ESS001",
        "device_type": "storage",
        "is_online": True,
        "power_kw": -10.0,
        "storage_soc": 65.5,
        "updated_at": datetime.now(),
    }
    status = DeviceStatusResponse(**data)
    assert status.storage_soc == 65.5


# ==================== A-03: Repository 测试 ====================

from app.repositories.device_repository import DeviceRepository


def test_ensure_default_devices(db_session):
    """第一次初始化生成三条设备"""
    repo = DeviceRepository(db_session)
    devices = repo.ensure_default_devices()

    assert len(devices) == 3
    codes = [d.device_code for d in devices]
    assert "PV001" in codes
    assert "ESS001" in codes
    assert "CHG001" in codes


def test_ensure_default_devices_idempotent(db_session):
    """第二次初始化仍为三条（幂等）"""
    repo = DeviceRepository(db_session)
    # 第一次
    devices1 = repo.ensure_default_devices()
    # 第二次
    devices2 = repo.ensure_default_devices()

    assert len(devices1) == 3
    assert len(devices2) == 3
    # 数据库里应该只有 3 条记录
    all_devices = repo.list_devices()
    assert len(all_devices) == 3


def test_get_by_id(db_session):
    """可以按 ID 查询设备"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    device = repo.get_by_id(1)
    assert device is not None
    assert device.device_code == "PV001"


def test_get_by_code(db_session):
    """可以按编码查询设备"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    device = repo.get_by_code("ESS001")
    assert device is not None
    assert device.device_name == "模拟储能"


def test_list_devices_by_type(db_session):
    """可以按类型筛选设备"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    pv_devices = repo.list_devices(device_type="pv")
    assert len(pv_devices) == 1
    assert pv_devices[0].device_code == "PV001"

    storage_devices = repo.list_devices(device_type="storage")
    assert len(storage_devices) == 1
    assert storage_devices[0].device_code == "ESS001"


def test_get_nonexistent_device(db_session):
    """不存在的设备返回 None，不抛异常"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    device = repo.get_by_id(999)
    assert device is None

    device = repo.get_by_code("NONEXISTENT")
    assert device is None


# ==================== A-04: Service 测试 ====================

import pytest
from app.services.device_service import DeviceService, DeviceNotFoundError
from app.repositories.device_repository import DeviceRepository


def test_get_devices(db_session):
    """测试获取设备列表"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    service = DeviceService(repo)
    devices = service.get_devices()

    assert len(devices) == 3
    assert devices[0].device_code == "PV001"
    assert devices[0].device_type == "pv"


def test_get_devices_by_type(db_session):
    """测试按类型筛选设备列表"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    service = DeviceService(repo)
    pv_devices = service.get_devices(device_type="pv")

    assert len(pv_devices) == 1
    assert pv_devices[0].device_code == "PV001"

    storage_devices = service.get_devices(device_type="storage")
    assert len(storage_devices) == 1
    assert storage_devices[0].device_code == "ESS001"


def test_get_device_detail(db_session):
    """测试获取设备详情"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    service = DeviceService(repo)
    device = service.get_device(1)

    assert device.id == 1
    assert device.device_code == "PV001"
    assert device.device_name == "模拟光伏"
    assert device.created_at is not None


def test_get_device_not_found(db_session):
    """测试获取不存在的设备抛异常"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()

    service = DeviceService(repo)
    with pytest.raises(DeviceNotFoundError):
        service.get_device(999)

# ==================== A-05: API 测试（使用临时文件数据库） ====================

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import create_app
from app.api.devices import get_db as api_get_db
from app.repositories.device_repository import DeviceRepository
from app.database import Base


def test_api_list_devices(tmp_path):
    """测试：设备列表 API 返回 200"""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[api_get_db] = override_get_db
    client = TestClient(app)

    # 初始化默认设备
    repo = DeviceRepository(TestingSessionLocal())
    repo.ensure_default_devices()

    response = client.get("/api/devices")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["device_code"] == "PV001"


def test_api_list_devices_by_type(tmp_path):
    """测试：按类型筛选设备 API"""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[api_get_db] = override_get_db
    client = TestClient(app)

    repo = DeviceRepository(TestingSessionLocal())
    repo.ensure_default_devices()

    response = client.get("/api/devices?device_type=pv")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["device_code"] == "PV001"


def test_api_get_device_detail(tmp_path):
    """测试：获取设备详情 API"""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[api_get_db] = override_get_db
    client = TestClient(app)

    repo = DeviceRepository(TestingSessionLocal())
    repo.ensure_default_devices()

    response = client.get("/api/devices/1")
    assert response.status_code == 200
    data = response.json()
    assert data["device_code"] == "PV001"


def test_api_get_device_not_found(tmp_path):
    """测试：不存在的设备返回 404"""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[api_get_db] = override_get_db
    client = TestClient(app)

    repo = DeviceRepository(TestingSessionLocal())
    repo.ensure_default_devices()

    response = client.get("/api/devices/999")
    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


# ==================== A-06: 设备状态映射测试 ====================

from datetime import datetime
from app.schemas.common import SystemState
from app.services.device_service import DeviceService, DeviceNotFoundError
from app.repositories.device_repository import DeviceRepository
import pytest


def test_device_status_pv(db_session):
    """测试：pv 设备状态映射（power_kw = pv_power, storage_soc = None）"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()
    service = DeviceService(repo)

    state = SystemState(
        timestamp=datetime.now(),
        simulated_hour=12.0,
        pv_power=45.6,
        load_power=30.0,
        storage_power=5.0,
        storage_soc=60.0,
    )
    status = service.get_device_status(1, state)
    assert status.device_code == "PV001"
    assert status.device_type == "pv"
    assert status.power_kw == 45.6
    assert status.storage_soc is None


def test_device_status_storage(db_session):
    """测试：storage 设备状态映射（power_kw = storage_power, storage_soc = storage_soc）"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()
    service = DeviceService(repo)

    state = SystemState(
        timestamp=datetime.now(),
        simulated_hour=12.0,
        pv_power=45.6,
        load_power=30.0,
        storage_power=-10.0,
        storage_soc=75.5,
    )
    status = service.get_device_status(2, state)
    assert status.device_code == "ESS001"
    assert status.device_type == "storage"
    assert status.power_kw == -10.0
    assert status.storage_soc == 75.5


def test_device_status_charger(db_session):
    """测试：charger 设备状态映射（power_kw = load_power, storage_soc = None）"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()
    service = DeviceService(repo)

    state = SystemState(
        timestamp=datetime.now(),
        simulated_hour=12.0,
        pv_power=45.6,
        load_power=30.0,
        storage_power=5.0,
        storage_soc=60.0,
    )
    status = service.get_device_status(3, state)
    assert status.device_code == "CHG001"
    assert status.device_type == "charger"
    assert status.power_kw == 30.0
    assert status.storage_soc is None


def test_device_status_not_found(db_session):
    """测试：不存在设备返回 DeviceNotFoundError"""
    repo = DeviceRepository(db_session)
    repo.ensure_default_devices()
    service = DeviceService(repo)

    state = SystemState(
        timestamp=datetime.now(),
        simulated_hour=12.0,
        pv_power=45.6,
        load_power=30.0,
        storage_power=5.0,
        storage_soc=60.0,
    )
    with pytest.raises(DeviceNotFoundError):
        service.get_device_status(999, state)
# ==================== A-07: 页面测试 ====================

# ==================== A-RC2-03: 修正页面测试 ====================

def test_devices_page_returns_200(tmp_path):
    """测试：设备管理页面可访问"""
    from app.main import create_app
    from app.config import Settings
    from fastapi.testclient import TestClient

    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        loop_seconds=60,
        history_limit=10,
    )
    app = create_app(start_background=False, settings=settings)

    # 使用 with 确保 lifespan 完整执行
    with TestClient(app) as client:
        response = client.get("/devices")
        assert response.status_code == 200
        assert "设备管理" in response.text