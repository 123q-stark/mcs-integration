"""
MILP 储能调度优化器（使用 scipy.optimize.milp + HiGHS）。
目标：最小化购电费用 + 小峰值惩罚。

符号约定（冻结契约 03）：
- storage_power > 0 表示放电（向电网送电）
- storage_power < 0 表示充电（从电网吸收）
- grid_import >= 0（从电网购电）
- grid_export >= 0（向电网售电）
- 功率平衡：storage_power + grid_import - grid_export = load - pv
"""
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from datetime import datetime
from typing import Dict, Any

from .interfaces import EnergyOptimizer
from app.schemas.algorithm import OptimizationResult, SchedulePoint


class MilpBatteryOptimizer(EnergyOptimizer):
    def __init__(self, time_step_hours: float = 0.25):
        self.time_step = time_step_hours

    def optimize(self, request: Dict[str, Any]) -> OptimizationResult:
        try:
            load = np.array(request['load_forecast'])
            pv = np.array(request['pv_forecast'])
            price = np.array(request['price_series'])
            soc0 = request['current_soc']
            cap = request['battery_capacity_kwh']
            soc_min = request['soc_min']
            soc_max = request['soc_max']
            p_charge_max = request['charge_power_max']
            p_discharge_max = request['discharge_power_max']
            max_import = request['max_import_power']
            allow_export = request.get('allow_export', False)
            max_export = request.get('max_export_power', 0.0)

            n = 96
            dt = self.time_step

            num_p = n
            num_g = n
            num_e = n
            total_vars = num_p + num_g + num_e
            peak_idx = total_vars
            total_vars_with_peak = total_vars + 1

            # ===== 目标函数 =====
            c = np.zeros(total_vars_with_peak)
            # 购电成本：grid_import 有成本
            c[num_p:num_p+num_g] = price * dt
            # 峰值惩罚：小权重
            c[peak_idx] = 0.001
            # ===== T06 修复：grid_export 添加微小惩罚，防止滥用售电变量 =====
            # 如果允许售电，grid_export 有微小成本，使优化器在满足平衡时
            # 优先使用储能（p_storage）而非售电，从而使电价影响储能调度。
            c[num_p+num_g:num_p+num_g+num_e] = 0.001

            A_eq = []
            b_eq = []
            A_ub = []
            b_ub = []

            # 功率平衡: p_storage + grid_import - grid_export = load - pv
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                row[t] = 1.0
                row[num_p + t] = 1.0
                row[num_p + num_g + t] = -1.0
                A_eq.append(row)
                b_eq.append(load[t] - pv[t])

            # grid_import <= max_import
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                row[num_p + t] = 1.0
                A_ub.append(row)
                b_ub.append(max_import)

            # grid_export 约束
            if allow_export:
                for t in range(n):
                    row = np.zeros(total_vars_with_peak)
                    row[num_p + num_g + t] = 1.0
                    A_ub.append(row)
                    b_ub.append(max_export)
            else:
                for t in range(n):
                    row = np.zeros(total_vars_with_peak)
                    row[num_p + num_g + t] = 1.0
                    A_eq.append(row)
                    b_eq.append(0.0)

            # peak >= grid_import_t → grid_import_t - peak <= 0
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                row[num_p + t] = 1.0
                row[peak_idx] = -1.0
                A_ub.append(row)
                b_ub.append(0.0)

            # SOC 约束
            cum_coeff = -100.0 * dt / cap
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                for k in range(t + 1):
                    row[k] = 1.0
                upper = (soc_min - soc0) / cum_coeff
                lower = (soc_max - soc0) / cum_coeff
                A_ub.append(row)
                b_ub.append(upper)
                row_neg = -row
                A_ub.append(row_neg)
                b_ub.append(-lower)

            # 边界
            bounds = []
            for _ in range(n):
                bounds.append((-p_charge_max, p_discharge_max))
            for _ in range(n):
                bounds.append((0, None))
            for _ in range(n):
                bounds.append((0, None))
            bounds.append((0, None))

            A_eq_mat = np.array(A_eq)
            b_eq_arr = np.array(b_eq)
            A_ub_mat = np.array(A_ub)
            b_ub_arr = np.array(b_ub)

            result = milp(
                c=c,
                constraints=[
                    LinearConstraint(A_eq_mat, b_eq_arr, b_eq_arr),
                    LinearConstraint(A_ub_mat, np.full_like(b_ub_arr, -np.inf), b_ub_arr)
                ],
                bounds=Bounds(
                    lb=[b[0] if b[0] is not None else -np.inf for b in bounds],
                    ub=[b[1] if b[1] is not None else np.inf for b in bounds]
                )
            )

            if not result.success:
                return OptimizationResult(
                    optimizer_name="MILP",
                    created_at=datetime.utcnow(),
                    success=False,
                    objective_value=None,
                    schedule=[],
                    message=f"MILP求解失败: {result.message}"
                )

            p_storage_opt = result.x[:n]
            grid_import_opt = result.x[num_p:num_p+n]

            schedule = []
            soc = soc0
            for t in range(n):
                soc = soc0 + np.sum(-p_storage_opt[:t+1] * dt / cap * 100.0)
                soc = max(soc_min - 0.01, min(soc_max + 0.01, soc))
                schedule.append(SchedulePoint(
                    timestamp=datetime.utcnow(),
                    storage_power_target_kw=float(p_storage_opt[t]),
                    predicted_soc=float(soc)
                ))

            objective = np.sum(price * grid_import_opt * dt)

            return OptimizationResult(
                optimizer_name="MILP",
                created_at=datetime.utcnow(),
                success=True,
                objective_value=float(objective),
                schedule=schedule,
                message="Optimization successful"
            )

        except Exception as e:
            return OptimizationResult(
                optimizer_name="MILP",
                created_at=datetime.utcnow(),
                success=False,
                objective_value=None,
                schedule=[],
                message=f"MILP异常: {str(e)}"
            )