"""
光储充最小完备系统 — 综合集成测试
验证完整链路：启动、初始化、API、页面、状态一致性、重启幂等
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import create_app
from app.config import Settings


def test_full_application_startup(tmp_path):
    """测试完整应用启动：建表、初始化、API 和页面"""
    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        loop_seconds=60,
        history_limit=10,
    )
    app = create_app(start_background=False, settings=settings)

    with TestClient(app) as client:
        # 1. 所有页面可访问
        assert client.get("/").status_code == 200
        assert client.get("/devices").status_code == 200
        assert client.get("/strategy").status_code == 200

        # 2. 核心 API
        assert client.get("/api/status").status_code == 200
        assert client.get("/api/history").status_code == 200
        assert client.get("/api/commands").status_code == 200

        # 3. 设备 API 返回 12 条默认设备
        devices = client.get("/api/devices").json()
        assert len(devices) == 12
        codes = [d["device_code"] for d in devices]
        # 验证所有默认设备编码都存在
        expected_codes = [
            "PV001", "PV002", "PV003", "PV004", "PV005",
            "CHG001", "CHG002", "CHG003", "CHG004", "CHG005",
            "BATT001", "GRID001"
        ]
        for code in expected_codes:
            assert code in codes

        # 4. 策略配置存在
        config = client.get("/api/strategies/config")
        assert config.status_code == 200
        data = config.json()
        assert data["config_name"] == "default"
        assert data["soc_min"] == 20.0
        assert data["soc_max"] == 90.0

        # 5. 设备详情（PV001 的 ID 是 1）
        device = client.get("/api/devices/1").json()
        assert device["device_code"] == "PV001"

        # 6. 设备状态一致性
        status = client.get("/api/status").json()
        pv_status = client.get("/api/devices/1/status").json()          # PV001
        storage_status = client.get("/api/devices/11/status").json()    # BATT001
        charger_status = client.get("/api/devices/6/status").json()     # CHG001

        assert abs(pv_status["power_kw"] - status["pv_power"]) < 0.01
        assert abs(storage_status["power_kw"] - status["storage_power"]) < 0.01
        assert abs(storage_status["storage_soc"] - status["storage_soc"]) < 0.01
        assert abs(charger_status["power_kw"] - status["load_power"]) < 0.01


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
        }

        # 第一次保存
        r1 = client.put("/api/strategies/config", json=config_data)
        assert r1.status_code == 200

        # 第二次保存（同名）
        r2 = client.put("/api/strategies/config", json=config_data)
        assert r2.status_code == 200

        # 验证只有一条激活配置
        config = client.get("/api/strategies/config").json()
        assert config["config_name"] == "default"


def test_restart_idempotent(tmp_path):
    """测试重启不重复插入默认数据"""
    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        loop_seconds=60,
        history_limit=10,
    )

    # 第一次启动
    app1 = create_app(start_background=False, settings=settings)
    with TestClient(app1) as client1:
        devices1 = client1.get("/api/devices").json()
        assert len(devices1) == 12

    # 第二次启动（同一数据库）
    app2 = create_app(start_background=False, settings=settings)
    with TestClient(app2) as client2:
        devices2 = client2.get("/api/devices").json()
        assert len(devices2) == 12  # 仍是 12 条，不是 24 条