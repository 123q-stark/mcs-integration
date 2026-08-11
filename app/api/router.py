# app/api/router.py
"""
API 路由统一注册中心
所有子路由都在这里集中挂载
"""
from fastapi import APIRouter
from .system import router as system_router
from .devices import router as devices_router
from .strategies import router as strategies_router

router = APIRouter()

# 挂载所有子路由
router.include_router(system_router)
router.include_router(devices_router)
router.include_router(strategies_router)