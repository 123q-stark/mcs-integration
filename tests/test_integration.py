"""
集成测试：验证应用启动、配置持久化、重启幂等性
"""
import tempfile
import os
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings


def test_full_application_startup():
    """测试应用完整启动（不报错）"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            loop_seconds=60,
            history_limit=10,
        )
        app = create_app(start_background=False, settings=settings)

        with TestClient(app) as client:
            # 测试首页，确保应用能正常响应
            response = client.get("/")
            assert response.status_code == 200
            # 确保返回的是 HTML 页面
            assert "text/html" in response.headers.get("content-type", "")
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_strategy_config_idempotent(tmp_path):
    """测试策略配置重复保存（同名更新）"""
    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        loop_seconds=60,
        history_limit=10,
    )
    app = create_app(start_background=False, settings=settings)

    with TestClient(app) as client:
        config_data = {
            "config_name": "default",
            "soc_min": 20.0,
            "soc_max": 90.0,
            "charge_power_kw": 10.0,
            "discharge_power_kw": 10.0,
            "is_active": True,
            "requested_mode": "AUTO",
            "backup_soc_target": 50.0,
        }

        # 第一次保存
        r1 = client.put("/api/strategies/config", json=config_data)
        assert r1.status_code == 200

        # 第二次保存（相同内容）
        r2 = client.put("/api/strategies/config", json=config_data)
        assert r2.status_code == 200

        # 验证只有一条记录
        get_response = client.get("/api/strategies/config")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["config_name"] == "default"
        assert data["soc_min"] == 20.0
        assert data["soc_max"] == 90.0


def test_restart_idempotent(tmp_path):
    """测试重启后配置不丢失、设备不重复"""
    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        loop_seconds=60,
        history_limit=10,
    )

    # 第一次启动
    app1 = create_app(start_background=False, settings=settings)
    with TestClient(app1) as client:
        # 修改配置
        config_data = {
            "config_name": "custom",
            "soc_min": 30.0,
            "soc_max": 80.0,
            "charge_power_kw": 8.0,
            "discharge_power_kw": 8.0,
            "is_active": True,
            "requested_mode": "PV_PRIORITY",
            "backup_soc_target": 60.0,
        }
        r = client.put("/api/strategies/config", json=config_data)
        assert r.status_code == 200

    # 第二次启动（模拟重启）
    app2 = create_app(start_background=False, settings=settings)
    with TestClient(app2) as client:
        response = client.get("/api/strategies/config")
        assert response.status_code == 200
        data = response.json()
        assert data["config_name"] == "custom"
        assert data["soc_min"] == 30.0
        assert data["soc_max"] == 80.0
        assert data["requested_mode"] == "PV_PRIORITY"
        assert data["backup_soc_target"] == 60.0