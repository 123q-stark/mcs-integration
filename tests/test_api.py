from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_page_and_api(tmp_path: Path):
    db_file = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        loop_seconds=60,
        history_limit=10,
    )
    app = create_app(start_background=False, settings=settings)

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "光储充管理系统" in page.text
        status = client.get("/api/status")
        assert status.status_code == 200
        payload = status.json()
        assert {
            "pv_power",
            "load_power",
            "storage_power",
            "storage_soc",
            "action",
            "strategy_message",
            "updated_at",
        }.issubset(payload)

        history = client.get("/api/history")
        assert history.status_code == 200
        assert len(history.json()) >= 1

        reset = client.post("/api/reset")
        assert reset.status_code == 200
        assert reset.json()["success"] is True
