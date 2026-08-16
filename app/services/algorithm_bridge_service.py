"""
算法桥接服务（B-07）
B 调用 C 算法的统一入口
负责：
1. 从 A 读取历史数据
2. 从 B 获取价格和策略约束
3. 组装 C 算法需要的标准输入
4. 调用 C 的算法模块（XGBoost / Baseline）
5. 校验结果并返回
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd

from sqlalchemy.orm import Session

from app.algorithms.baseline_forecast import HistoricalSameSlotBaseline
from app.algorithms.xgboost_forecast import XGBoostLoadForecaster, XGBoostPVForecaster
from app.algorithms.milp_dispatch import MilpBatteryOptimizer
from app.algorithms.auto_mode import AutoModeSelectorRule
from app.schemas.algorithm import ForecastResult, ForecastPoint, OptimizationResult

logger = logging.getLogger(__name__)


class AlgorithmBridgeService:
    """算法桥接服务 - B 调用 C 算法的统一入口"""

    def __init__(self, db: Session, device_read_port=None):
        self.db = db
        self.device_read_port = device_read_port

        # ===== v1.3 完善：初始化 XGBoost 和 Baseline =====
        self.load_forecaster = XGBoostLoadForecaster(min_history_days=7)
        self.pv_forecaster = XGBoostPVForecaster(min_history_days=7)
        self.baseline_forecaster = HistoricalSameSlotBaseline(n_days=7)
        self.optimizer = MilpBatteryOptimizer()
        self.auto_selector = AutoModeSelectorRule()

        # 缓存训练好的模型（避免每次重新训练）
        self._load_model_trained = False
        self._pv_model_trained = False

    def set_device_port(self, device_read_port):
        self.device_read_port = device_read_port

    # =========================================================
    # v1.3 完善：负荷预测（优先 XGBoost，失败回退 Baseline）
    # =========================================================
    def get_load_forecast(self, history_days: int = 30) -> ForecastResult:
        """
        获取负荷预测（次日96点）
        优先使用 XGBoost，失败时回退到 Baseline
        """
        try:
            # 1. 从 A 获取历史数据
            history = self._get_history_data('load', history_days)
            if history is None or len(history) < 96:
                logger.warning("历史数据不足（<96点），使用 Baseline 预测")
                return self._get_baseline_forecast('load', history_days)

            # 2. 尝试 XGBoost 预测
            try:
                # 检查历史是否足够训练（至少7天）
                if len(history) >= 7 * 96:
                    # 训练模型（如果还没训练或需要重新训练）
                    self.load_forecaster.fit(history)
                    self._load_model_trained = True

                # 如果模型已训练，进行预测
                if self._load_model_trained:
                    start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    result = self.load_forecaster.predict_next_day(history, start_time)
                    if result and len(result.points) == 96:
                        logger.info(f"XGBoost 负荷预测成功: {len(result.points)} 点")
                        return result
                else:
                    logger.warning("XGBoost 负荷模型未训练，使用 Baseline")

            except Exception as e:
                logger.warning(f"XGBoost 负荷预测失败: {e}，回退到 Baseline")

            # 3. 回退到 Baseline
            return self._get_baseline_forecast('load', history_days)

        except Exception as e:
            logger.error(f"负荷预测异常: {e}")
            return self._get_empty_forecast('load')

    # =========================================================
    # v1.3 完善：PV 预测（优先 XGBoost，失败回退 Baseline）
    # =========================================================
    def get_pv_forecast(self, history_days: int = 30) -> ForecastResult:
        """
        获取 PV 预测（次日96点）
        优先使用 XGBoost，失败时回退到 Baseline
        """
        try:
            history = self._get_history_data('pv', history_days)
            if history is None or len(history) < 96:
                logger.warning("PV历史数据不足（<96点），使用 Baseline 预测")
                return self._get_baseline_forecast('pv', history_days)

            try:
                if len(history) >= 7 * 96:
                    self.pv_forecaster.fit(history)
                    self._pv_model_trained = True

                if self._pv_model_trained:
                    start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    result = self.pv_forecaster.predict_next_day(history, start_time)
                    if result and len(result.points) == 96:
                        # 确保 PV 预测非负
                        for p in result.points:
                            if p.value_kw < 0:
                                p.value_kw = 0.0
                        logger.info(f"XGBoost PV 预测成功: {len(result.points)} 点")
                        return result
                else:
                    logger.warning("XGBoost PV 模型未训练，使用 Baseline")

            except Exception as e:
                logger.warning(f"XGBoost PV 预测失败: {e}，回退到 Baseline")

            return self._get_baseline_forecast('pv', history_days)

        except Exception as e:
            logger.error(f"PV 预测异常: {e}")
            return self._get_empty_forecast('pv')

    # =========================================================
    # 辅助方法
    # =========================================================
    def _get_baseline_forecast(self, target: str, history_days: int) -> ForecastResult:
        """使用 Baseline 进行预测（7天滑动平均）"""
        history = self._get_history_data(target, history_days)
        if history is None or len(history) < 96:
            return self._get_empty_forecast(target)

        start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return self.baseline_forecaster.predict_next_day(history, start_time, target=target)

    def _get_empty_forecast(self, target: str) -> ForecastResult:
        """返回空预测（全0），用于错误兜底"""
        from app.schemas.algorithm import ForecastPoint
        start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        points = []
        for i in range(96):
            dt = start_time + timedelta(minutes=15 * i)
            points.append(ForecastPoint(timestamp=dt, value_kw=0.0))
        return ForecastResult(
            model_name="Empty_Fallback",
            target=target,
            created_at=datetime.now(),
            step_minutes=15,
            points=points,
            mae=None,
            rmse=None
        )

    # =========================================================
    # 从 A 获取历史数据
    # =========================================================
    def _get_history_data(self, target: str, days: int) -> Optional[pd.DataFrame]:
        """从数据库获取历史数据"""
        if self.device_read_port is None:
            logger.warning("device_read_port 未设置，无法获取历史数据")
            return None

        try:
            if hasattr(self.device_read_port, 'get_history_data'):
                return self.device_read_port.get_history_data(target, days)
            return self._get_history_from_db(target, days)
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return None

    # ===== v1.6 修复：移除 cutoff 时间限制，查询所有历史数据 =====
    def _get_history_from_db(self, target: str, days: int) -> Optional[pd.DataFrame]:
        """从数据库直接读取历史数据（查询所有历史数据，不限制时间范围）"""
        try:
            from app.models.device_telemetry import DeviceTelemetry

            # ===== v1.6 修复：移除 cutoff 时间限制 =====
            # 原因：生成的历史数据时间戳可能早于 datetime.now() - days
            # 导致查询为空，MILP 无法获取训练数据
            # cutoff = datetime.now() - timedelta(days=days)

            if target == 'load':
                charger_codes = [f"CHG{i:03d}" for i in range(1, 6)]
                with self.db.session() as session:
                    # ===== 移除 created_at >= cutoff 条件 =====
                    records = session.query(DeviceTelemetry).filter(
                        DeviceTelemetry.device_code.in_(charger_codes)
                    ).order_by(DeviceTelemetry.created_at).all()

                    if not records:
                        logger.warning(f"未找到充电桩历史数据: {charger_codes}")
                        return None

                    df = pd.DataFrame([{
                        'timestamp': r.created_at,
                        'device_code': r.device_code,
                        'power_kw': r.power_kw or 0
                    } for r in records])

                    grouped = df.groupby('timestamp')['power_kw'].sum().reset_index()
                    grouped.columns = ['timestamp', 'load_kw']
                    return grouped.sort_values('timestamp')

            elif target == 'pv':
                pv_codes = [f"PV{i:03d}" for i in range(1, 6)]
                with self.db.session() as session:
                    # ===== 移除 created_at >= cutoff 条件 =====
                    records = session.query(DeviceTelemetry).filter(
                        DeviceTelemetry.device_code.in_(pv_codes)
                    ).order_by(DeviceTelemetry.created_at).all()

                    if not records:
                        logger.warning(f"未找到 PV 历史数据: {pv_codes}")
                        return None

                    df = pd.DataFrame([{
                        'timestamp': r.created_at,
                        'device_code': r.device_code,
                        'power_kw': r.power_kw or 0
                    } for r in records])

                    grouped = df.groupby('timestamp')['power_kw'].sum().reset_index()
                    grouped.columns = ['timestamp', 'pv_kw']
                    return grouped.sort_values('timestamp')

            return None

        except Exception as e:
            logger.error(f"从数据库读取历史数据失败: {e}")
            return None

    # =========================================================
    # v1.3 完善：储能调度优化（修复：避免重复获取配置）
    # =========================================================
    def get_optimization(self, load_forecast: ForecastResult, pv_forecast: ForecastResult,
                         price_series: List[float], current_soc: float,
                         battery_capacity_kwh: float = 200.0) -> OptimizationResult:
        try:
            from app.repositories.strategy_repository import StrategyRepository
            from app.repositories.grid_strategy_repository import GridStrategyRepository

            # ===== 修复：在 with 块内获取所有配置 =====
            with self.db.session() as session:
                strategy_repo = StrategyRepository(session)
                grid_repo = GridStrategyRepository(session)
                strategy_config = strategy_repo.get_active_config()
                grid_config = grid_repo.get_config()

            if strategy_config is None:
                soc_min, soc_max = 20.0, 90.0
                charge_power_max, discharge_power_max = 10.0, 10.0
            else:
                soc_min = strategy_config.soc_min
                soc_max = strategy_config.soc_max
                charge_power_max = strategy_config.charge_power_kw
                discharge_power_max = strategy_config.discharge_power_kw

            request = {
                'load_forecast': [p.value_kw for p in load_forecast.points],
                'pv_forecast': [p.value_kw for p in pv_forecast.points],
                'price_series': price_series,
                'current_soc': current_soc,
                'battery_capacity_kwh': battery_capacity_kwh,
                'soc_min': soc_min,
                'soc_max': soc_max,
                'charge_power_max': charge_power_max,
                'discharge_power_max': discharge_power_max,
                'max_import_power': grid_config.max_import_power_kw,
                'allow_export': grid_config.allow_export,
                'max_export_power': grid_config.max_export_power_kw,
            }
            return self.optimizer.optimize(request)
        except Exception as e:
            logger.error(f"优化失败: {e}")
            return OptimizationResult(
                optimizer_name="MILP",
                created_at=datetime.now(),
                success=False,
                objective_value=None,
                schedule=[],
                message=f"优化失败: {str(e)}"
            )

    def get_auto_mode(self, context: Dict[str, Any]) -> str:
        try:
            return self.auto_selector.select(context)
        except Exception as e:
            logger.error(f"AUTO模式推荐失败: {e}")
            return "SAFE"