# app/api/system.py
"""
系统状态、历史、控制命令和重置接口
"""
from fastapi import APIRouter, Request
from app.schemas import (
    CommandItem,
    HistoryItem,
    ResetResponse,
    StatusResponse,
)

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    """获取当前系统实时状态"""
    return request.app.state.service.get_status()


@router.get("/history", response_model=list[HistoryItem])
async def get_history(request: Request):
    """获取历史运行数据（用于绘制曲线）"""
    return request.app.state.service.get_history()


@router.get("/commands", response_model=list[CommandItem])
async def get_commands(request: Request):
    """获取最近的控制命令记录"""
    return request.app.state.service.get_commands(limit=10)


@router.post("/reset", response_model=ResetResponse)
async def reset_demo(request: Request):
    """重置系统状态和数据库记录"""
    await request.app.state.service.reset()
    return ResetResponse(success=True, message="演示状态和数据库记录已重置。")