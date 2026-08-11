"""
MILP 储能调度优化器（使用 scipy.optimize.milp + HiGHS）。
目标：最小化购电费用 + 小峰值惩罚。
"""
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from datetime import datetime
from typing import List, Dict, Any

from .interfaces import EnergyOptimizer
from app.schemas.algorithm import OptimizationResult, SchedulePoint


class MilpBatteryOptimizer(EnergyOptimizer):
    def __init__(self, time_step_hours: float = 0.25):
        self.time_step = time_step_hours

    def optimize(self, request: Dict[str, Any]) -> OptimizationResult:
        """
        request 字典应包含以下键（见 interfaces.py）：
            load_forecast: List[float] (96)
            pv_forecast: List[float] (96)
            price_series: List[float] (96)
            current_soc: float
            battery_capacity_kwh: float
            soc_min: float
            soc_max: float
            charge_power_max: float   # 充电功率绝对值上限
            discharge_power_max: float # 放电功率绝对值上限
            max_import_power: float
            allow_export: bool
            max_export_power: float    # 若 allow_export=True 有效
        """
        try:
            # 解析输入
            load = np.array(request['load_forecast'])
            pv = np.array(request['pv_forecast'])
            price = np.array(request['price_series'])
            soc0 = request['current_soc']
            cap = request['battery_capacity_kwh']
            soc_min = request['soc_min']
            soc_max = request['soc_max']
            p_charge_max = request['charge_power_max']   # >0
            p_discharge_max = request['discharge_power_max']  # >0
            max_import = request['max_import_power']
            allow_export = request.get('allow_export', False)
            max_export = request.get('max_export_power', 0.0)

            n = 96
            dt = self.time_step

            # 决策变量: 每个时刻的储能功率 p_storage (正=放电, 负=充电)
            # 同时引入网格购电 g (>=0) 和售电 e (>=0)
            # 功率平衡: load - pv = g - e + p_storage  =>  g - e = load - pv - p_storage
            # 但我们希望以 g 作为变量，e 由平衡决定，但为了便于约束，我们使用 g 和 e 两个变量，并增加约束 g*e=0 (互补)
            # 但互补非线性难以处理，可以使用两个变量并增加 big-M 约束，或直接允许双向功率，但目标函数中购电费用仅对购电部分。
            # 简化：我们允许 grid_power 可以为正或负，但若为负（售电），则不计费用（或收益），但我们不鼓励售电，除非允许。
            # 更简单：定义 grid_power = load - pv - p_storage，然后惩罚购电，并限制 grid_power <= max_import 和 grid_power >= -max_export (若允许)
            # 这样目标仅考虑购电费用 (positive part of grid_power)
            # 使用线性化：引入辅助变量 grid_import >= 0, grid_export >= 0, 且 grid_import - grid_export = load - pv - p_storage, grid_import <= max_import, grid_export <= max_export (若允许)
            # 目标：sum(price * grid_import * dt) + 小惩罚 * max(grid_import)
            # 我们实现这种线性化。

            # 变量顺序: [p_storage_0, p_storage_1, ..., p_storage_95, grid_import_0..95, grid_export_0..95]
            # 共 3n 个变量
            num_p = n
            num_g = n
            num_e = n
            total_vars = num_p + num_g + num_e

            # 目标系数：储能功率无直接成本，grid_import 有成本，grid_export 无收益（或小惩罚）
            c = np.zeros(total_vars)
            c[num_p:num_p+num_g] = price * dt  # 购电费用
            # 增加峰值惩罚：在目标中加入一个额外的变量 peak，表示最大购电功率，我们通过约束 peak >= grid_import_t，目标加 small*peak
            # 为了简单，直接增加一个峰值变量 p_peak，在末尾
            # 重新规划：变量 = [p_storage, grid_import, grid_export, peak]
            # 添加峰值变量
            peak_idx = total_vars
            total_vars_with_peak = total_vars + 1
            c_peak = np.zeros(total_vars_with_peak)
            c_peak[:total_vars] = c
            c_peak[peak_idx] = 0.001  # 小惩罚系数

            # 约束矩阵
            A_eq = []  # 等式：grid_import - grid_export = load - pv - p_storage (每个时刻)
            b_eq = []
            # 不等式：约束变量上下界，以及 peak >= grid_import_t
            A_ub = []
            b_ub = []

            # 填充等式约束
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                row[t] = 1.0  # p_storage
                row[num_p + t] = -1.0  # -grid_import
                row[num_p + num_g + t] = 1.0  # +grid_export
                # 等式右边 = load - pv (注意符号：p_storage - grid_import + grid_export = load - pv)
                # 即 p_storage - grid_import + grid_export = load - pv
                A_eq.append(row)
                b_eq.append(load[t] - pv[t])

            # 不等式：grid_import <= max_import
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                row[num_p + t] = 1.0
                A_ub.append(row)
                b_ub.append(max_import)

            # 若允许售电，则 grid_export <= max_export
            if allow_export:
                for t in range(n):
                    row = np.zeros(total_vars_with_peak)
                    row[num_p + num_g + t] = 1.0
                    A_ub.append(row)
                    b_ub.append(max_export)
            else:
                # 禁止售电：grid_export = 0
                for t in range(n):
                    row = np.zeros(total_vars_with_peak)
                    row[num_p + num_g + t] = 1.0
                    A_eq.append(row)
                    b_eq.append(0.0)

            # 不等式：peak >= grid_import_t
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                row[num_p + t] = -1.0
                row[peak_idx] = 1.0
                A_ub.append(row)
                b_ub.append(0.0)

            # SOC递推约束：SOC_t = SOC_{t-1} + (-p_storage_t * dt) / cap * 100
            # 写成线性约束：SOC_{t} - SOC_{t-1} + (100*dt/cap)*p_storage_t = 0
            # 引入 SOC 变量？也可以直接写成不等式：SOC_min <= SOC_t <= SOC_max
            # 我们用变量表示 SOC_t（在p_storage基础上），但为简化，我们直接用p_storage的累积来约束。
            # 更稳妥：使用线性约束表示 SOC 上下限：SOC0 + sum_{k=0..t} (-p_storage_k * dt)/cap *100 在 [soc_min, soc_max]
            # 即 -100*dt/cap * sum(p_storage_0..t) + SOC_t = SOC0，但 SOC_t 不是变量，我们可以用累积和约束。
            # 我们引入新的辅助变量 soc_t (96个)，但会增加变量数，更简单：直接用线性不等式。
            # 方法：使用 A_ub 和 b_ub，约束：SOC_min <= SOC0 - (100*dt/cap) * cumsum(p_storage[0..t]) <= SOC_max
            # 即 cumsum(p_storage) <= (SOC0 - SOC_min) * cap / (100*dt)  和 cumsum(p_storage) >= (SOC0 - SOC_max) * cap / (100*dt)
            cum_coeff = -100 * dt / cap  # 因为 SOC_t = SOC0 + cum_coeff * sum(p_storage[0..t])
            # 对于每个 t:
            # SOC_min <= SOC0 + cum_coeff * sum_{k=0..t} p_storage_k <= SOC_max
            # => sum_{k=0..t} p_storage_k <= (SOC_max - SOC0) / cum_coeff  如果 cum_coeff <0，需变号
            # 由于 cum_coeff < 0，不等式变号：
            # sum_{k=0..t} p_storage_k >= (SOC_max - SOC0) / cum_coeff   (因为除以负数)
            # 和 sum_{k=0..t} p_storage_k <= (SOC_min - SOC0) / cum_coeff
            # 直接实现：
            for t in range(n):
                row = np.zeros(total_vars_with_peak)
                for k in range(t+1):
                    row[k] = 1.0
                # 上限：sum <= (SOC_min - SOC0) / cum_coeff  (注意 cum_coeff 负，结果正)
                upper = (SOC_min - SOC0) / cum_coeff
                lower = (SOC_max - SOC0) / cum_coeff  # 因为 cum_coeff 负，lower 更小（负值）
                # 实际上，cum_coeff<0，SOC0 + cum_coeff*sum 介于 SOC_min 和 SOC_max
                # 推导：
                # SOC_min <= SOC0 + cum_coeff*S <= SOC_max
                # => (SOC_min - SOC0)/cum_coeff >= S >= (SOC_max - SOC0)/cum_coeff   (注意除负数变号)
                # 即 S >= (SOC_max - SOC0)/cum_coeff  且 S <= (SOC_min - SOC0)/cum_coeff
                # 因为 cum_coeff<0, (SOC_max - SOC0)/cum_coeff 为负（如果 SOC_max>SOC0），(SOC_min - SOC0)/cum_coeff 为正？ 计算一下
                # 例如 SOC0=50, SOC_max=90, SOC_min=20, cum_coeff=-0.1 => (90-50)/-0.1 = -400, (20-50)/-0.1 = 300
                # 所以 S 必须 >= -400 且 <= 300，即下限 -400，上限 300。但 S 是功率累计，可能负或正。这样约束合理。
                # 添加两个不等式：S <= upper 和 S >= lower
                A_ub.append(row)
                b_ub.append((SOC_min - SOC0) / cum_coeff)  # 上限
                # 下限转为 -S <= -lower
                row_lower = -row
                A_ub.append(row_lower)
                b_ub.append(-(SOC_max - SOC0) / cum_coeff)  # 因为 -S <= -lower

            # 变量边界：p_storage 上下限
            bounds = []
            # p_storage: 充电为负，放电为正
            for _ in range(n):
                bounds.append((-p_charge_max, p_discharge_max))
            # grid_import >= 0
            for _ in range(n):
                bounds.append((0, None))
            # grid_export >= 0
            for _ in range(n):
                bounds.append((0, None))
            # peak >= 0
            bounds.append((0, None))

            # 求解
            A_eq_mat = np.array(A_eq)
            b_eq_arr = np.array(b_eq)
            A_ub_mat = np.array(A_ub)
            b_ub_arr = np.array(b_ub)

            # 调用 milp
            result = milp(
                c=c_peak,
                constraints=[
                    LinearConstraint(A_eq_mat, b_eq_arr, b_eq_arr),
                    LinearConstraint(A_ub_mat, np.full_like(b_ub_arr, -np.inf), b_ub_arr)
                ],
                bounds=Bounds(lb=[b[0] if b[0] is not None else -np.inf for b in bounds],
                              ub=[b[1] if b[1] is not None else np.inf for b in bounds]),
                method='highs'
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

            # 提取结果
            p_storage_opt = result.x[:n]
            # 计算每个时刻的预测SOC
            soc = soc0
            schedule = []
            for t in range(n):
                # p_storage 为正放电，负充电
                delta_soc = -p_storage_opt[t] * dt / cap * 100
                soc = soc0 + np.sum(-p_storage_opt[:t+1] * dt / cap * 100)
                # 截断到物理边界，但应满足约束
                schedule.append(SchedulePoint(
                    timestamp=datetime.utcnow(),  # 实际需要时间，但可后续赋值
                    storage_power_target_kw=float(p_storage_opt[t]),
                    predicted_soc=float(soc)
                ))

            # 计算目标值（购电费用）
            grid_import = result.x[num_p:num_p+n]
            objective = np.sum(price * grid_import * dt)

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