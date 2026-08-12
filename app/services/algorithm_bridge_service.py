"""
算法桥接服务（B-07）
B 调用 C 算法的统一入口
负责：
1. 从 A 读取历史数据
2. 从 B 获取价格和策略约束
3. 组装 C 算法需要的标准输入
4. 调用 C 的算法模块
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
from app.schemas.algorithm import ForecastResult, OptimizationResult

logger = logging.getLogger(__name__)


class AlgorithmBridgeService:
    """算法桥接服务 - B 调用 C 算法的统一入口"""

    def __init__(self, db: Session, device_read_port=None):
        """
        初始化算法桥接服务
        
        Args:
            db: 数据库会话
            device_read_port: 设备读取端口（用于获取历史数据）
        """
        self.db = db
        self.device_read_port = device_read_port
        
        # 初始化算法实例
        self.load_forecaster = XGBoostLoadForecaster(min_history_days=7)
        self.pv_forecaster = XGBoostPVForecaster(min_history_days=7)
        self.baseline_forecaster = HistoricalSameSlotBaseline(n_days=7)
        self.optimizer = MilpBatteryOptimizer()
        self.auto_selector = AutoModeSelectorRule()

    def set_device_port(self, device_read_port):
        """设置设备读取端口"""
        self.device_read_port = device_read_port

    def get_load_forecast(self, history_days: int = 30) -> ForecastResult:
        """
        获取负荷预测（次日96点）
        
        Args:
            history_days: 使用最近多少天的历史数据
        
        Returns:
            ForecastResult: 预测结果
        """
        try:
            # 1. 从 A 获取历史数据
            history = self._get_history_data('load', history_days)
            if history is None or len(history) < 96:
                logger.warning("历史数据不足，使用Baseline预测")
                return self._get_baseline_forecast('load', history_days)

            # 2. 尝试 XGBoost 预测
            try:
                # 训练模型
                self.load_forecaster.fit(history)
                start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                result = self.load_forecaster.predict_next_day(history, start_time)
                logger.info(f"XGBoost负荷预测成功: {len(result.points)} 点")
                return result
            except Exception as e:
                logger.warning(f"XGBoost负荷预测失败: {e}，回退到Baseline")
                return self._get_baseline_forecast('load', history_days)

        except Exception as e:
            logger.error(f"负荷预测异常: {e}")
            # 返回空结果
            return ForecastResult(
                model_name="Error",
                target="load",
                created_at=datetime.now(),
                step_minutes=15,
                points=[],
                mae=None,
                rmse=None
            )

    def get_pv_forecast(self, history_days: int = 30) -> ForecastResult:
        """
        获取PV预测（次日96点）
        """
        try:
            history = self._get_history_data('pv', history_days)
            if history is None or len(history) < 96:
                logger.warning("PV历史数据不足，使用Baseline预测")
                return self._get_baseline_forecast('pv', history_days)

            try:
                self.pv_forecaster.fit(history)
                start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                result = self.pv_forecaster.predict_next_day(history, start_time)
                logger.info(f"XGBoost PV预测成功: {len(result.points)} 点")
                return result
            except Exception as e:
                logger.warning(f"XGBoost PV预测失败: {e}，回退到Baseline")
                return self._get_baseline_forecast('pv', history_days)

        except Exception as e:
            logger.error(f"PV预测异常: {e}")
            return ForecastResult(
                model_name="Error",
                target="pv",
                created_at=datetime.now(),
                step_minutes=15,
                points=[],
                mae=None,
                rmse=None
            )

    def _get_baseline_forecast(self, target: str, history_days: int) -> ForecastResult:
        """使用Baseline进行预测"""
        history = self._get_history_data(target, history_days)
        if history is None or len(history) < 96:
            # 生成默认预测（全0）
            start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            from app.schemas.algorithm import ForecastPoint
            points = []
            for i in range(96):
                dt = start_time + timedelta(minutes=15*i)
                points.append(ForecastPoint(timestamp=dt, value_kw=0.0))
            return ForecastResult(
                model_name="Baseline_Fallback",
                target=target,
                created_at=datetime.now(),
                step_minutes=15,
                points=points,
                mae=None,
                rmse=None
            )
        
        start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return self.baseline_forecaster.predict_next_day(history, start_time, target=target)

    def _get_history_data(self, target: str, days: int) -> Optional[pd.DataFrame]:
        """
        从 A 获取历史数据
        
        Args:
            target: 'load' 或 'pv'
            days: 查询天数
        
        Returns:
            DataFrame 包含 timestamp 和 {target}_kw 列
        """
        if self.device_read_port is None:
            logger.warning("device_read_port 未设置，无法获取历史数据")
            return None

        try:
            # 通过 device_read_port 获取历史数据
            # 这里假设 A 实现了 get_history_data 方法
            if hasattr(self.device_read_port, 'get_history_data'):
                return self.device_read_port.get_history_data(target, days)
            
            # 如果 A 没有实现，尝试从数据库直接读取
            return self._get_history_from_db(target, days)
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return None

    def _get_history_from_db(self, target: str, days: int) -> Optional[pd.DataFrame]:
        """从数据库直接读取历史数据（临时方案）"""
        try:
            from app.models.device_telemetry import DeviceTelemetryModel
            
            cutoff = datetime.now() - timedelta(days=days)
            device_code = None
            
            if target == 'load':
                # 负荷 = 所有充电桩功率之和
                charger_codes = [f"CHG{i:03d}" for i in range(1, 6)]
                query = self.db.query(DeviceTelemetryModel).filter(
                    DeviceTelemetryModel.device_code.in_(charger_codes),
                    DeviceTelemetryModel.created_at >= cutoff
                ).order_by(DeviceTelemetryModel.created_at)
                
                records = query.all()
                if not records:
                    return None
                
                # 按时间聚合
                df = pd.DataFrame([{
                    'timestamp': r.created_at,
                    'device_code': r.device_code,
                    'power_kw': r.power_kw or 0
                } for r in records])
                
                # 按时间分组求和
                grouped = df.groupby('timestamp')['power_kw'].sum().reset_index()
                grouped.columns = ['timestamp', 'load_kw']
                return grouped.sort_values('timestamp')
                
            elif target == 'pv':
                # PV = 所有光伏设备功率之和
                pv_codes = [f"PV{i:03d}" for i in range(1, 6)]
                query = self.db.query(DeviceTelemetryModel).filter(
                    DeviceTelemetryModel.device_code.in_(pv_codes),
                    DeviceTelemetryModel.created_at >= cutoff
                ).order_by(DeviceTelemetryModel.created_at)
                
                records = query.all()
                if not records:
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

    def get_optimization(self, load_forecast: ForecastResult, pv_forecast: ForecastResult,
                         price_series: List[float], current_soc: float,
                         battery_capacity_kwh: float = 200.0) -> OptimizationResult:
        """
        获取储能调度优化结果
        
        Args:
            load_forecast: 负荷预测结果
            pv_forecast: PV预测结果
            price_series: 96点电价序列
            current_soc: 当前SOC
            battery_capacity_kwh: 电池容量
        
        Returns:
            OptimizationResult: 优化结果
        """
        try:
            # 从策略配置获取约束
            from app.repositories.strategy_repository import StrategyRepository
            from app.repositories.grid_strategy_repository import GridStrategyRepository
            
            strategy_repo = StrategyRepository(self.db)
            grid_repo = GridStrategyRepository(self.db)
            
            strategy_config = strategy_repo.get_active_config()
            grid_config = grid_repo.get_config()
            
            if strategy_config is None:
                logger.warning("未找到策略配置，使用默认值")
                soc_min, soc_max = 20.0, 90.0
                charge_power_max, discharge_power_max = 10.0, 10.0
            else:
                soc_min = strategy_config.soc_min
                soc_max = strategy_config.soc_max
                charge_power_max = strategy_config.charge_power_kw
                discharge_power_max = strategy_config.discharge_power_kw

            # 构建优化请求
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
        """
        获取 AUTO 模式推荐
        
        Args:
            context: 包含当前系统状态的字典
        
        Returns:
            str: 推荐模式
        """
        try:
            return self.auto_selector.select(context)
        except Exception as e:
            logger.error(f"AUTO模式推荐失败: {e}")
            return "SAFE"
