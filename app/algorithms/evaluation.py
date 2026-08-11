"""
评价指标：MAE, RMSE。
"""
import numpy as np
from typing import List


def mae(actual: List[float], predicted: List[float]) -> float:
    return float(np.mean(np.abs(np.array(actual) - np.array(predicted))))


def rmse(actual: List[float], predicted: List[float]) -> float:
    return float(np.sqrt(np.mean((np.array(actual) - np.array(predicted))**2)))