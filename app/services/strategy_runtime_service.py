"""
策略运行服务（B-08/B-09 完善 - v1.4）
负责：
1. 从 A 读取当前系统状态
2. 从 B 获取策略配置
3. 根据 requested_mode 决定是否调用 C 算法（MILP/AUTO）
4. 生成 ControlDecision（包含 schedule 信息）
5. 调用 A 执行
6. 保存策略运行记录（含 schedule JSON）
"""
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import json
import math

from sqlalchemy.exc import OperationalError

from app.schemas import SystemState, ControlDecision, ControlExecutionResult
from app.schemas.algorithm import ForecastResult, OptimizationResult, SchedulePoint
from app.services.algorithm_bridge_service import AlgorithmBridgeService
from app.strategies.fixed_rule import FixedRuleStrategy

logger = logging.getLogger(__name__)


class StrategyRuntimeService:
    """策略运行编排服务（v1.4 完善）"""

    def __init__(
        self,
        db,
        device_read_port=None,
        device_execution_port=None,
    ):
        self.db = db
        self.device_read_port = device_read_port
        self.device_execution_port = device_execution_port

        self.bridge = AlgorithmBridgeService(db, device_read_port)
        self.fixed_rule = FixedRuleStrategy()

        # 运行时缓存
        self.current_state: Optional[SystemState] = None
        self.current_decision: Optional[ControlDecision] = None
        self.current_execution: Optional[ControlExecutionResult] = None
        self.load_forecast: Optional[ForecastResult] = None
        self.pv_forecast: Optional[ForecastResult] = None
        self.optimization: Optional[OptimizationResult] = None
        self.effective_mode: str = "PV_PRIORITY"
        self.fallback_used: bool = False

    def set_device_ports(self, read_port, execution_port):
        self.device_read_port = read_port
        self.device_execution_port = execution_port
        self.bridge.set_device_port(read_port)

    def run_cycle(self) -> Dict[str, Any]:
        """
        执行一个完整的策略运行周期（v1.4 支持 AUTO 和 MILP）
        """
        try:
            logger.info("===== 开始策略运行周期 =====")

            # 1. 读取系统状态
            state = self._get_system_state()
            if state is None:
                logger.error("无法获取系统状态")
                return {"success": False, "error": "无法获取系统状态"}
            self.current_state = state
            logger.info(f"系统状态: SOC={state.storage_soc}%, PV={state.pv_power}kW, Load={state.load_power}kW, Hour={state.simulated_hour}")

            # 2. 读取策略配置
            config = self._get_strategy_config()
            if config is None:
                logger.error("无法获取策略配置")
                return {"success": False, "error": "无法获取策略配置"}

            requested_mode = config.requested_mode
            effective_mode = requested_mode
            fallback_used = False

            load_forecast = None
            pv_forecast = None
            optimization = None

            logger.info(f"当前 requested_mode = {requested_mode}")

            # 3. 根据 requested_mode 决定是否调用 C 算法
            if requested_mode in ["ECONOMIC_SCHEDULE", "AUTO", "GRID_BACKUP"]:
                logger.info("进入优化分支（requested_mode 符合条件）")
                try:
                    # 获取预测
                    logger.info("开始获取负荷预测...")
                    load_forecast = self.bridge.get_load_forecast(history_days=30)
                    self.load_forecast = load_forecast
                    if load_forecast:
                        logger.info(f"负荷预测获取成功，点数={len(load_forecast.points)}，模型={load_forecast.model_name}")
                    else:
                        logger.warning("负荷预测返回 None")

                    logger.info("开始获取 PV 预测...")
                    pv_forecast = self.bridge.get_pv_forecast(history_days=30)
                    self.pv_forecast = pv_forecast
                    if pv_forecast:
                        logger.info(f"PV 预测获取成功，点数={len(pv_forecast.points)}，模型={pv_forecast.model_name}")
                    else:
                        logger.warning("PV 预测返回 None")

                    # 如果有预测数据，尝试优化
                    if load_forecast and load_forecast.points and pv_forecast and pv_forecast.points:
                        logger.info(f"预测数据有效，开始获取价格序列...")
                        price_series = self._get_price_series()
                        logger.info(f"价格序列长度={len(price_series)}")

                        logger.info("开始调用 MILP 优化...")
                        optimization = self.bridge.get_optimization(
                            load_forecast=load_forecast,
                            pv_forecast=pv_forecast,
                            price_series=price_series,
                            current_soc=state.storage_soc,
                        )
                        self.optimization = optimization

                        if optimization:
                            logger.info(f"MILP 优化返回，success={optimization.success}, 调度点数={len(optimization.schedule) if optimization.schedule else 0}, message={optimization.message}")
                            if optimization.success and optimization.schedule:
                                effective_mode = "ECONOMIC_SCHEDULE"
                                logger.info("=== 使用 MILP 优化调度 ===")
                            else:
                                logger.warning("MILP 优化失败或返回空结果，将回退到 FixedRule")
                        else:
                            logger.error("optimization 为 None")
                    else:
                        logger.warning(f"预测数据无效: load_forecast={bool(load_forecast)}, load_points={len(load_forecast.points) if load_forecast else 0}, pv_forecast={bool(pv_forecast)}, pv_points={len(pv_forecast.points) if pv_forecast else 0}")

                except Exception as e:
                    import traceback
                    logger.error(f"C算法调用异常: {e}\n{traceback.format_exc()}")
                    fallback_used = True
            else:
                logger.info(f"当前 requested_mode={requested_mode}，不触发优化分支")

            # 4. 如果 requested_mode == "AUTO"，调用 AUTO 推荐算法
            if requested_mode == "AUTO" and optimization and optimization.success:
                # 使用 AUTO 模式推荐
                auto_context = {
                    "current_soc": state.storage_soc,
                    "backup_soc_target": config.backup_soc_target,
                    "forecast_available": load_forecast is not None and len(load_forecast.points) > 0,
                    "schedule_available": optimization is not None and optimization.success,
                    "any_device_error": False,  # 可扩展
                    "current_price_level": self._get_current_price_level(state.simulated_hour),
                    "pv_power": state.pv_power,
                    "load_power": state.load_power,
                }
                try:
                    recommended_mode = self.bridge.get_auto_mode(auto_context)
                    if recommended_mode in ["ECONOMIC_SCHEDULE", "GRID_BACKUP", "PV_PRIORITY", "SAFE"]:
                        effective_mode = recommended_mode
                        logger.info(f"AUTO 推荐模式: {recommended_mode}")
                except Exception as e:
                    logger.warning(f"AUTO 推荐失败: {e}，保持当前模式")

            # 5. 生成控制决策
            if optimization and optimization.success and optimization.schedule:
                logger.info("基于 MILP 生成决策")
                decision = self._generate_decision_from_optimization(
                    state, optimization, effective_mode
                )
                decision.source = "milp"
            else:
                logger.info("使用 FixedRule 生成决策")
                decision = self.fixed_rule.calculate(state, config)
                # 根据 requested_mode 调整 effective_mode
                if requested_mode == "SAFE":
                    effective_mode = "SAFE"
                else:
                    effective_mode = "PV_PRIORITY"
                fallback_used = True
                decision.source = "fixed_rule"

            # 设置 decision 的 mode 和 source
            decision.mode = effective_mode
            decision.created_at = datetime.now()
            self.current_decision = decision
            self.effective_mode = effective_mode
            self.fallback_used = fallback_used

            # 6. 调用 A 执行
            if self.device_execution_port:
                execution_result = self.device_execution_port.execute(decision)
                self.current_execution = execution_result
            else:
                execution_result = ControlExecutionResult(
                    success=False,
                    storage_power_actual_kw=0,
                    charger_results=[],
                    message="执行端口未设置",
                    executed_at=datetime.now(),
                )

            # 7. 计算 overall_success（A 执行失败时整体失败）
            if isinstance(execution_result, dict):
                execution_success = execution_result.get("success", False)
            else:
                execution_success = execution_result.success

            # 8. 保存运行记录（包含 schedule JSON）
            run_record = self._save_run_record(
                state=state,
                decision=decision,
                execution=execution_result,
                requested_mode=requested_mode,
                effective_mode=effective_mode,
                fallback_used=fallback_used,
                load_forecast=load_forecast,
                pv_forecast=pv_forecast,
                optimization=optimization,
            )

            logger.info("===== 策略运行周期完成 =====")

            # 最终返回：overall_success 取决于 A 执行是否成功
            overall_success = execution_success

            return {
                "success": overall_success,
                "decision": decision,
                "execution": execution_result,
                "effective_mode": effective_mode,
                "fallback_used": fallback_used,
                "run_id": run_record.get("id") if run_record else None,
                "load_forecast": load_forecast,
                "pv_forecast": pv_forecast,
                "optimization": optimization,
                "schedule": optimization.schedule if (optimization and optimization.success) else [],
            }

        except Exception as e:
            logger.exception(f"策略运行失败: {e}")
            return {"success": False, "error": str(e)}

    def _get_system_state(self) -> Optional[SystemState]:
        if self.device_read_port is None:
            logger.warning("device_read_port 未设置")
            return None
        try:
            if hasattr(self.device_read_port, 'get_system_state'):
                return self.device_read_port.get_system_state()
            return None
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return None

    def _get_strategy_config(self):
        try:
            from app.repositories.strategy_repository import StrategyRepository
            with self.db.session() as session:
                repo = StrategyRepository(session)
                return repo.get_active_config()
        except Exception as e:
            logger.error(f"获取策略配置失败: {e}")
            return None

    def _get_price_series(self) -> List[float]:
        try:
            from app.repositories.price_repository import PriceRepository
            with self.db.session() as session:
                repo = PriceRepository(session)
                config = repo.get_config()
                prices = []
                for i in range(96):
                    hour = i // 4
                    if 10 <= hour < 15 or 18 <= hour < 21:
                        prices.append(config.peak_price)
                    elif 0 <= hour < 7 or 23 <= hour < 24:
                        prices.append(config.valley_price)
                    else:
                        prices.append(config.flat_price)
                return prices
        except Exception as e:
            logger.error(f"获取电价序列失败: {e}")
            return [0.5] * 96

    # ===== B-P1-05 + v1.6: 使用仿真时间而非系统时间 =====
    def _get_current_price_level(self, simulated_hour: float) -> str:
        """根据仿真时间获取当前电价级别"""
        try:
            from app.repositories.price_repository import PriceRepository
            with self.db.session() as session:
                repo = PriceRepository(session)
                config = repo.get_config()
                hour = int(simulated_hour) % 24
                if 10 <= hour < 15 or 18 <= hour < 21:
                    return "peak"
                elif 0 <= hour < 7 or 23 <= hour < 24:
                    return "valley"
                else:
                    return "flat"
        except Exception:
            return "flat"

    def _generate_decision_from_optimization(
        self, state: SystemState, optimization: OptimizationResult, mode: str
    ) -> ControlDecision:
        """从 MILP 优化结果生成当前时刻的决策"""
        current_hour = state.simulated_hour
        slot_index = int(current_hour / 0.25) % 96
        if slot_index < len(optimization.schedule):
            target = optimization.schedule[slot_index].storage_power_target_kw
            message = f"MILP调度: 目标储能功率 {target:.2f} kW"
        else:
            target = 0
            message = "无有效调度点，待机"
        return ControlDecision(
            storage_power_target=target,
            action="charge" if target < 0 else "discharge" if target > 0 else "idle",
            message=message,
            created_at=datetime.now(),
            source="milp",
            mode=mode,
        )

    # ===== v1.6: 修复版 - 使用短 Session 写入 =====
    def _save_run_record(
        self,
        state: SystemState,
        decision: ControlDecision,
        execution: ControlExecutionResult,
        requested_mode: str,
        effective_mode: str,
        fallback_used: bool,
        load_forecast: Optional[ForecastResult] = None,
        pv_forecast: Optional[ForecastResult] = None,
        optimization: Optional[OptimizationResult] = None,
    ) -> Optional[Dict]:
        """
        保存策略运行记录（使用短生命周期 Session）
        修复说明：
        - 删除临时禁用 workaround
        - 使用 self.db.session() 短 Session（不自行创建 Database）
        - 记录追溯字段（forecast_model_load, forecast_model_pv, optimizer_name）
        """
        try:
            from app.repositories.strategy_run_repository import StrategyRunRepository
            from app.models.strategy_run import StrategyRunModel

            # 序列化预测和调度数据
            load_json = None
            if load_forecast and load_forecast.points:
                load_json = json.dumps([
                    {"timestamp": p.timestamp.isoformat(), "value": p.value_kw}
                    for p in load_forecast.points
                ])

            pv_json = None
            if pv_forecast and pv_forecast.points:
                pv_json = json.dumps([
                    {"timestamp": p.timestamp.isoformat(), "value": p.value_kw}
                    for p in pv_forecast.points
                ])

            schedule_json = None
            if optimization and optimization.schedule:
                schedule_json = json.dumps([
                    {
                        "timestamp": p.timestamp.isoformat(),
                        "power": p.storage_power_target_kw,
                        "soc": p.predicted_soc
                    }
                    for p in optimization.schedule
                ])

            # 处理 execution 可能是字典或对象
            if isinstance(execution, dict):
                exec_success = execution.get("success", False)
                exec_message = execution.get("message")
            else:
                exec_success = execution.success
                exec_message = execution.message

            # ✅ 使用注入的 self.db，每次写入创建短 Session
            with self.db.session() as session:
                repo = StrategyRunRepository(session)

                run_data = {
                    "created_at": datetime.now(),
                    "requested_mode": requested_mode,
                    "effective_mode": effective_mode,
                    "fallback_used": fallback_used,
                    "storage_power_target": decision.storage_power_target,
                    "action": decision.action,
                    "message": decision.message,
                    "source": decision.source,
                    "status": "success" if exec_success else "failed",
                    # 追溯字段
                    "forecast_model_load": load_forecast.model_name if load_forecast else None,
                    "forecast_model_pv": pv_forecast.model_name if pv_forecast else None,
                    "optimizer_name": optimization.optimizer_name if optimization else None,
                    "algorithm_message": decision.message if decision else None,
                    "execution_message": exec_message,
                    # JSON 字段
                    "load_forecast_json": load_json,
                    "pv_forecast_json": pv_json,
                    "schedule_json": schedule_json,
                }

                run = repo.create(run_data)
                logger.info(f"✅ 策略运行记录已保存: id={run.id}")
                return {"id": run.id}

        except Exception as e:
            logger.error(f"❌ 保存策略运行记录失败: {e}")
            # 保存失败不应阻塞策略执行，返回 None 表示未记录
            return None

    def get_latest_run(self) -> Optional[Dict]:
        try:
            from app.models.strategy_run import StrategyRunModel
            with self.db.session() as session:
                record = session.query(StrategyRunModel).order_by(
                    StrategyRunModel.created_at.desc()
                ).first()
                if record is None:
                    return None
                return {
                    "id": record.id,
                    "created_at": record.created_at,
                    "requested_mode": record.requested_mode,
                    "effective_mode": record.effective_mode,
                    "fallback_used": record.fallback_used,
                    "storage_power_target": record.storage_power_target,
                    "action": record.action,
                    "message": record.message,
                    "source": record.source,
                    "status": record.status,
                    # v1.6: 追溯字段
                    "forecast_model_load": record.forecast_model_load,
                    "forecast_model_pv": record.forecast_model_pv,
                    "optimizer_name": record.optimizer_name,
                    "algorithm_message": record.algorithm_message,
                    "execution_message": record.execution_message,
                    # JSON 字段
                    "load_forecast_json": record.load_forecast_json,
                    "pv_forecast_json": record.pv_forecast_json,
                    "schedule_json": record.schedule_json,
                }
        except Exception as e:
            logger.error(f"获取最近运行记录失败: {e}")
            return None

    def get_current_status(self) -> Dict[str, Any]:
        return {
            "has_state": self.current_state is not None,
            "has_decision": self.current_decision is not None,
            "has_execution": self.current_execution is not None,
            "effective_mode": self.effective_mode,
            "fallback_used": self.fallback_used,
            "decision": self.current_decision.dict() if self.current_decision else None,
        }