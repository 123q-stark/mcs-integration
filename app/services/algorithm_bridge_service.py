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
    def get_load_forecast(self, history_days: int = 30, current_timestamp: Optional[datetime] = None) -> ForecastResult:
        """
        获取负荷预测（次日96点）
        优先使用 XGBoost，失败时回退到 Baseline
        - history_days: 历史数据天数
        - current_timestamp: 当前仿真时间（用于计算预测起始时间，符合 07-2 规范）
        """
        try:
            # 1. 从 A 获取历史数据
            history = self._get_history_data('load', history_days)
            if history is None or len(history) < 96:
                logger.warning("历史数据不足（<96点），返回不可用预测")
                return self._get_empty_forecast('load', "Insufficient historical data (<96 points)")

            # 2. 尝试 XGBoost 预测
            try:
                # 检查历史是否足够训练（至少7天）
                if len(history) >= 7 * 96:
                    # 训练模型（如果还没训练或需要重新训练）
                    self.load_forecaster.fit(history)
                    self._load_model_trained = True

                # 如果模型已训练，进行预测
                if self._load_model_trained:
                    # =============================================================
                    # ✅ 修复：使用仿真时间计算预测起始时间
                    # 修改前：使用 datetime.now()（真实系统时间）
                    # 修改后：使用 current_timestamp（仿真时间），符合 07-2 规范
                    # =============================================================
                    if current_timestamp is None:
                        base_time = datetime.now()
                    else:
                        base_time = current_timestamp
                    start_time = base_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

                    result = self.load_forecaster.predict_next_day(history, start_time)
                    if result and len(result.points) == 96:
                        # P0-01: 标记为可用
                        result.available = True
                        result.message = "XGBoost load forecast"
                        logger.info(f"XGBoost 负荷预测成功: {len(result.points)} 点")
                        return result
                else:
                    logger.warning("XGBoost 负荷模型未训练，使用 Baseline")

            except Exception as e:
                logger.warning(f"XGBoost 负荷预测失败: {e}，回退到 Baseline")

            # 3. 回退到 Baseline
            return self._get_baseline_forecast('load', history_days, current_timestamp)

        except Exception as e:
            logger.error(f"负荷预测异常: {e}")
            return self._get_empty_forecast('load', f"Prediction error: {str(e)}")

    # =========================================================
    # v1.3 完善：PV 预测（优先 XGBoost，失败回退 Baseline）
    # =========================================================
    def get_pv_forecast(self, history_days: int = 30, current_timestamp: Optional[datetime] = None) -> ForecastResult:
        """
        获取 PV 预测（次日96点）
        优先使用 XGBoost，失败时回退到 Baseline
        - history_days: 历史数据天数
        - current_timestamp: 当前仿真时间（用于计算预测起始时间，符合 07-2 规范）
        """
        try:
            history = self._get_history_data('pv', history_days)
            if history is None or len(history) < 96:
                logger.warning("PV历史数据不足（<96点），返回不可用预测")
                return self._get_empty_forecast('pv', "Insufficient historical data (<96 points)")

            try:
                if len(history) >= 7 * 96:
                    self.pv_forecaster.fit(history)
                    self._pv_model_trained = True

                if self._pv_model_trained:
                    # =============================================================
                    # ✅ 修复：使用仿真时间计算预测起始时间
                    # 修改前：使用 datetime.now()（真实系统时间）
                    # 修改后：使用 current_timestamp（仿真时间），符合 07-2 规范
                    # =============================================================
                    if current_timestamp is None:
                        base_time = datetime.now()
                    else:
                        base_time = current_timestamp
                    start_time = base_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

                    result = self.pv_forecaster.predict_next_day(history, start_time)
                    if result and len(result.points) == 96:
                        # 确保 PV 预测非负
                        for p in result.points:
                            if p.value_kw < 0:
                                p.value_kw = 0.0
                        # P0-01: 标记为可用
                        result.available = True
                        result.message = "XGBoost PV forecast"
                        logger.info(f"XGBoost PV 预测成功: {len(result.points)} 点")
                        return result
                else:
                    logger.warning("XGBoost PV 模型未训练，使用 Baseline")

            except Exception as e:
                logger.warning(f"XGBoost PV 预测失败: {e}，回退到 Baseline")

            return self._get_baseline_forecast('pv', history_days, current_timestamp)

        except Exception as e:
            logger.error(f"PV 预测异常: {e}")
            return self._get_empty_forecast('pv', f"Prediction error: {str(e)}")

    # =========================================================
    # 辅助方法
    # =========================================================
    def _get_baseline_forecast(self, target: str, history_days: int, current_timestamp: Optional[datetime] = None) -> ForecastResult:
        """
        使用 Baseline 进行预测（7天滑动平均）
        - target: 'load' 或 'pv'
        - history_days: 历史数据天数
        - current_timestamp: 当前仿真时间（用于计算预测起始时间）
        """
        history = self._get_history_data(target, history_days)
        if history is None or len(history) < 96:
            return self._get_empty_forecast(target, "Insufficient historical data for baseline")

        # =============================================================
        # ✅ 修复：使用仿真时间计算预测起始时间
        # 修改前：使用 datetime.now()（真实系统时间）
        # 修改后：使用 current_timestamp（仿真时间），符合 07-2 规范
        # =============================================================
        if current_timestamp is None:
            base_time = datetime.now()
        else:
            base_time = current_timestamp
        start_time = base_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

        result = self.baseline_forecaster.predict_next_day(history, start_time, target=target)
        # P0-01: 标记为可用
        result.available = True
        result.message = "Baseline forecast (7-day rolling average)"
        return result

    # ==================== P0-01: 不可用预测 ====================
    def _get_empty_forecast(self, target: str, reason: str = "No valid forecast") -> ForecastResult:
        """
        返回不可用预测（P0-01 修复）
        返回 available=False，points=[]，不再返回 96 个 0 值
        """
        return ForecastResult(
            available=False,  # P0-01: 标记为不可用
            model_name="Unavailable",
            target=target,
            created_at=datetime.now(),
            step_minutes=15,
            points=[],  # P0-01: 空列表，不再是 96 个 0
            mae=None,
            rmse=None,
            message=reason  # P0-01: 说明原因
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

            if target == 'load':
                charger_codes = [f"CHG{i:03d}" for i in range(1, 6)]
                with self.db.session() as session:
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
    # v1.3 完善：储能调度优化
    # =========================================================
    def get_optimization(
        self,
        load_forecast: ForecastResult,
        pv_forecast: ForecastResult,
        price_series: List[float],
        current_soc: float,
        current_timestamp: Optional[datetime] = None,
        battery_capacity_kwh: float = 200.0
    ) -> OptimizationResult:
        """
        获取储能调度优化结果（96点）

        Args:
            load_forecast: 负荷预测结果
            pv_forecast: PV 预测结果
            price_series: 96 点电价序列
            current_soc: 当前 SOC
            current_timestamp: 当前仿真时间（07-2 要求使用仿真时间）
            battery_capacity_kwh: 电池容量

        Returns:
            OptimizationResult: MILP 优化结果
        """
        try:
            from app.repositories.strategy_repository import StrategyRepository
            from app.repositories.grid_strategy_repository import GridStrategyRepository

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

            # 如果未传入 current_timestamp，使用当前时间作为 fallback
            if current_timestamp is None:
                current_timestamp = datetime.now()

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
                'current_timestamp': current_timestamp,
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