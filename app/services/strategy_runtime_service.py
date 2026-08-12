"""
策略运行服务（B-08）
负责：
1. 从 A 读取当前系统状态
2. 从 B 获取策略配置
3. 调用 AlgorithmBridgeService 获取预测和优化
4. 生成 ControlDecision
5. 调用 A 执行
6. 保存策略运行记录
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import json

from app.schemas import SystemState, ControlDecision, ControlExecutionResult
from app.schemas.algorithm import ForecastResult, OptimizationResult
from app.services.algorithm_bridge_service import AlgorithmBridgeService
from app.strategies.fixed_rule import FixedRuleStrategy

logger = logging.getLogger(__name__)


class StrategyRuntimeService:
    """策略运行编排服务"""

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
        
        self.current_state: Optional[SystemState] = None
        self.current_decision: Optional[ControlDecision] = None
        self.current_execution: Optional[ControlExecutionResult] = None
        self.load_forecast: Optional[ForecastResult] = None
        self.pv_forecast: Optional[ForecastResult] = None
        self.optimization: Optional[OptimizationResult] = None

    def set_device_ports(self, read_port, execution_port):
        self.device_read_port = read_port
        self.device_execution_port = execution_port
        self.bridge.set_device_port(read_port)

    def run_cycle(self) -> Dict[str, Any]:
        try:
            state = self._get_system_state()
            if state is None:
                return {"success": False, "error": "无法获取系统状态"}
            self.current_state = state

            config = self._get_strategy_config()
            if config is None:
                return {"success": False, "error": "无法获取策略配置"}

            requested_mode = config.requested_mode
            effective_mode = requested_mode
            fallback_used = False

            load_forecast = None
            pv_forecast = None
            optimization = None

            # 获取预测（v1.3: 使用 AlgorithmBridgeService 获取 XGBoost 预测）
            if requested_mode in ["ECONOMIC_SCHEDULE", "AUTO", "GRID_BACKUP"]:
                try:
                    load_forecast = self.bridge.get_load_forecast(history_days=30)
                    pv_forecast = self.bridge.get_pv_forecast(history_days=30)
                    self.load_forecast = load_forecast
                    self.pv_forecast = pv_forecast
                    
                    if load_forecast.points and pv_forecast.points:
                        price_series = self._get_price_series()
                        optimization = self.bridge.get_optimization(
                            load_forecast=load_forecast,
                            pv_forecast=pv_forecast,
                            price_series=price_series,
                            current_soc=state.storage_soc,
                        )
                        self.optimization = optimization
                        
                        if optimization.success and optimization.schedule:
                            effective_mode = "ECONOMIC_SCHEDULE"
                except Exception as e:
                    logger.warning(f"C算法调用失败: {e}，回退到 FixedRule")
                    fallback_used = True

            if optimization and optimization.success and optimization.schedule:
                decision = self._generate_decision_from_optimization(
                    state, optimization, effective_mode
                )
            else:
                decision = self.fixed_rule.calculate(state, config)
                effective_mode = "PV_PRIORITY" if requested_mode != "SAFE" else "SAFE"
                fallback_used = True

            decision.source = "milp" if optimization and optimization.success else "fixed_rule"
            decision.mode = effective_mode
            decision.created_at = datetime.now()
            self.current_decision = decision

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

            # v1.3: 保存运行记录（包含预测数据）
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

            return {
                "success": True,
                "decision": decision,
                "execution": execution_result,
                "effective_mode": effective_mode,
                "fallback_used": fallback_used,
                "run_id": run_record.get("id") if run_record else None,
                "load_forecast": load_forecast,
                "pv_forecast": pv_forecast,
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

    def _get_price_series(self) -> list:
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

    def _generate_decision_from_optimization(
        self, state: SystemState, optimization: OptimizationResult, mode: str
    ) -> ControlDecision:
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
        try:
            from app.models.strategy_run import StrategyRunModel
            
            with self.db.session() as session:
                # v1.3: 序列化预测数据
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

                record = StrategyRunModel(
                    created_at=datetime.now(),
                    requested_mode=requested_mode,
                    effective_mode=effective_mode,
                    fallback_used=fallback_used,
                    storage_power_target=decision.storage_power_target,
                    action=decision.action,
                    message=decision.message,
                    source=decision.source,
                    status="success" if execution.success else "failed",
                    load_forecast_json=load_json,
                    pv_forecast_json=pv_json,
                    schedule_json=schedule_json,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                return {"id": record.id}
        except Exception as e:
            logger.error(f"保存运行记录失败: {e}")
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
            "decision": self.current_decision.dict() if self.current_decision else None,
        }
