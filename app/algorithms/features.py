"""
特征工程：为负荷和 PV 预测生成时序特征。
所有特征计算均基于历史 DataFrame，避免未来数据泄露。
"""
import numpy as np
import pandas as pd


def build_load_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    输入 df 必须包含列：timestamp, load_kw
    返回包含所有特征的 DataFrame（原数据 + 新特征）
    """
    df = df.copy()
    df = df.sort_values('timestamp').reset_index(drop=True)

    # 时间特征
    df['hour'] = df['timestamp'].dt.hour
    df['minute_slot'] = df['timestamp'].dt.minute // 15  # 0~3
    df['weekday'] = df['timestamp'].dt.weekday
    df['is_weekend'] = df['weekday'].isin([5, 6]).astype(int)

    # 滞后特征 (使用前值)
    df['lag_1'] = df['load_kw'].shift(1)
    df['lag_4'] = df['load_kw'].shift(4)   # 1小时前
    df['lag_96'] = df['load_kw'].shift(96) # 1天前

    # 滚动统计
    df['rolling_mean_4'] = df['load_kw'].rolling(4, min_periods=1).mean()
    df['rolling_mean_96'] = df['load_kw'].rolling(96, min_periods=1).mean()

    # 删除含 NaN 的行（前几行）
    # 对于预测时，我们不会删除，而是用前向填充，但这里作为训练，可以删掉
    df = df.dropna()
    return df


def build_pv_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    输入 df 必须包含列：timestamp, pv_kw
    返回特征 DataFrame
    """
    df = df.copy()
    df = df.sort_values('timestamp').reset_index(drop=True)

    # 时间特征（周期编码）
    df['hour'] = df['timestamp'].dt.hour
    df['minute_slot'] = df['timestamp'].dt.minute // 15
    df['sin_time'] = np.sin(2 * np.pi * (df['hour'] + df['minute_slot']/4) / 24)
    df['cos_time'] = np.cos(2 * np.pi * (df['hour'] + df['minute_slot']/4) / 24)

    # 滞后
    df['lag_96'] = df['pv_kw'].shift(96)
    df['rolling_mean_96'] = df['pv_kw'].rolling(96, min_periods=1).mean()

    # 如果有辐照度列，也可以加入，但文档允许只用时间+历史PV
    df = df.dropna()
    return df