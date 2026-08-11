from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, Settings
from app.database import Database
from app.devices.simulator import SimulatorAdapter
from app.services.system_service import EMSService
from app.strategies.fixed_rule import FixedRuleStrategy
from app.api.router import router as api_router

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def create_app(
        *,
        start_background: bool = True,
        settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_url)
    device = SimulatorAdapter()
    strategy = FixedRuleStrategy()
    service = EMSService(
        database=database,
        device=device,
        strategy=strategy,
        loop_seconds=settings.loop_seconds,
        history_limit=settings.history_limit,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 1. 创建所有数据库表
        database.create_tables()

        # 2. 初始化默认设备和策略配置
        from app.repositories.device_repository import DeviceRepository
        from app.repositories.strategy_repository import StrategyRepository

        with database.session() as db:
            DeviceRepository(db).ensure_default_devices()
            StrategyRepository(db).ensure_default_config()
            from app.repositories.strategy_device_repository import StrategyDeviceRepository
            StrategyDeviceRepository(db).init_default_configs()

        # 3. 存储 service 到 app.state
        app.state.database = database
        app.state.service = service

        # 4. 启动时先执行一次，保证页面第一次访问就有数据
        await service.run_cycle()

        # 5. 启动后台循环任务
        if start_background:
            await service.start()

        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(
        title="光储充管理系统",
        description="展示模拟设备、策略、数据库、API 和前端页面如何组成完整链路。",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 挂载静态文件目录
    app.mount(
        "/static",
        StaticFiles(directory=str(APP_DIR / "static")),
        name="static",
    )

    # 挂载 API 路由（所有 /api/* 接口都在这里）
    app.include_router(api_router)

    # ========== 首页路由 ==========
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"project_name": "光储充管理系统"},
        )

    # ========== 设备管理页面路由（A 部分） ==========
    @app.get("/devices", response_class=HTMLResponse)
    async def devices_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="devices.html",
            context={"project_name": "设备管理"},
        )

    # ========== 策略配置页面路由（B 部分） ==========
    @app.get("/strategy", response_class=HTMLResponse)
    async def strategy_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="strategy.html",
            context={"project_name": "光储充管理系统"},
        )

    return app