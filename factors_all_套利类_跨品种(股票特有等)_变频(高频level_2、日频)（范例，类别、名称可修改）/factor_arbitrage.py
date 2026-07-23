# -*- coding: utf-8 -*-

import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from backtest_optimize import cal_signal_metric, get_signal_weight, get_security_type
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


security_type_list = ["fund", "stock", "future_all", "option_c_all", "option_p_all"]



class ______价差配对类_____():
    pass

    
def resid(df, window=60):
    """
        基于滚动 OLS 回归残差计算跨品种套利因子。

    因子公式：
        resid = log(Y) - alpha - beta * log(X)

    参数：
        df: DataFrame
            价格透视表，行索引为日期，列索引为两个标的，值为 close。
        window: int
            滚动回归窗口，研报中取 60。

    返回：
        res_factor: DataFrame
            包含两个标的价格、alpha、beta、resid、resid_mean、resid_std。
    """
    # 2. 计算价差
    df = df.astype(float).sort_index().copy()

    if df.shape[1] != 2:
        raise ValueError("resid 因子要求输入恰好两个标的。")

    x_code = df.columns[0]
    y_code = df.columns[1]

    log_x = np.log(df[x_code].where(df[x_code] > 0))
    log_y = np.log(df[y_code].where(df[y_code] > 0))

    res_factor = df.copy()
    res_factor["alpha"] = np.nan
    res_factor["beta"] = np.nan
    res_factor["resid"] = np.nan
    res_factor["resid_mean"] = np.nan
    res_factor["resid_std"] = np.nan

    for end_idx in range(window - 1, len(df)):
        sample_x = log_x.iloc[end_idx - window + 1:end_idx + 1]
        sample_y = log_y.iloc[end_idx - window + 1:end_idx + 1]

        sample = pd.concat([sample_x, sample_y], axis=1).dropna()

        if len(sample) < window:
            continue

        x_values = sample.iloc[:, 0].to_numpy()
        y_values = sample.iloc[:, 1].to_numpy()

        x_matrix = np.column_stack([np.ones(len(x_values)), x_values])

        alpha, beta = np.linalg.lstsq(
            x_matrix,
            y_values,
            rcond=None
        )[0]

        resid_series = y_values - alpha - beta * x_values

        current_date = df.index[end_idx]

        res_factor.loc[current_date, "alpha"] = alpha
        res_factor.loc[current_date, "beta"] = beta
        res_factor.loc[current_date, "resid"] = resid_series[-1]
        res_factor.loc[current_date, "resid_mean"] = resid_series.mean()
        res_factor.loc[current_date, "resid_std"] = resid_series.std(ddof=1)

    return res_factor



def resid_signal(
    df,
    window=60,
    X=2,
    stop_loss_X=3,
    threshold_mode="absolute",
    backtest_trading_mode="backtest",
    **kwargs
):
    """
    基于 resid 因子值生成交易信号。

    参数：
        df: DataFrame
            框架传入的原始长表，至少包含 ts_code 和 close。
        window: int
            滚动回归窗口。
        X: float
            信号阈值参数。
            threshold_mode="absolute" 时，X 表示 X 倍标准差，例如 X=2。
            threshold_mode="quantile" 时，X 表示分位数，例如 X=0.8。
        stop_loss_X: float
            止损阈值，默认 3 倍标准差。
        threshold_mode: str
            "absolute" 或 "quantile"。
        backtest_trading_mode: str
            框架传入参数，默认 "backtest"。

    返回：
        signal: DataFrame
            日期 × ts_code 的信号表，1 做多，-1 做空，0 平仓。
        signal_weight: DataFrame
            日期 × ts_code 的权重表。
        res_optimize_metric: list
            框架绩效评价或寻优结果。
    """
    df_dataTrade = pd.pivot_table(
        df,
        index=df.index,
        columns="ts_code",
        values="close",
        aggfunc="mean"
    ).sort_index()

    df_dataTrade = df_dataTrade.reindex(
        columns=df["ts_code"].dropna().drop_duplicates().tolist()
    )

    security_type_dict = get_security_type(
        df["ts_code"].dropna().drop_duplicates().tolist()
    )

    security_num = sum(
        len(security_type_dict.get(k, []) or [])
        for k in security_type_list
    )

    if security_num != 2:
        print("error：resid_signal 要求 security_type_list 中的标的总数必须是 2")
        return pd.DataFrame()

    res_factor = resid(df_dataTrade.copy(), window=window)

    x_code = df_dataTrade.columns[0]
    y_code = df_dataTrade.columns[1]

    if threshold_mode == "absolute":
        signal_exp = f"""
pd.DataFrame(
    np.select(
        [
            (
                (res_factor["resid"] > res_factor["resid_mean"] + {X} * res_factor["resid_std"])
                & (res_factor["resid"] < res_factor["resid_mean"] + {stop_loss_X} * res_factor["resid_std"])
            ).to_numpy()[:, None],
            (
                (res_factor["resid"] < res_factor["resid_mean"] - {X} * res_factor["resid_std"])
                & (res_factor["resid"] > res_factor["resid_mean"] - {stop_loss_X} * res_factor["resid_std"])
            ).to_numpy()[:, None],
            (
                (abs(res_factor["resid"] - res_factor["resid_mean"]) < {X} * res_factor["resid_std"])
                | (abs(res_factor["resid"] - res_factor["resid_mean"]) > {stop_loss_X} * res_factor["resid_std"])
            ).to_numpy()[:, None],
        ],
        [
            [1, -1],
            [-1, 1],
            [0, 0],
        ],
        default=[np.nan, np.nan]
    ),
    index=res_factor.index,
    columns=["{x_code}", "{y_code}"]
)
"""

    elif threshold_mode == "quantile":
        res_factor["upper_quantile"] = res_factor["resid"].rolling(window).quantile(X)
        res_factor["lower_quantile"] = res_factor["resid"].rolling(window).quantile(1 - X)

        signal_exp = f"""
pd.DataFrame(
    np.select(
        [
            (
                (res_factor["resid"] > res_factor["upper_quantile"])
                & (res_factor["resid"] < res_factor["resid_mean"] + {stop_loss_X} * res_factor["resid_std"])
            ).to_numpy()[:, None],
            (
                (res_factor["resid"] < res_factor["lower_quantile"])
                & (res_factor["resid"] > res_factor["resid_mean"] - {stop_loss_X} * res_factor["resid_std"])
            ).to_numpy()[:, None],
            (
                (
                    (res_factor["resid"] <= res_factor["upper_quantile"])
                    & (res_factor["resid"] >= res_factor["lower_quantile"])
                )
                | (abs(res_factor["resid"] - res_factor["resid_mean"]) > {stop_loss_X} * res_factor["resid_std"])
            ).to_numpy()[:, None],
        ],
        [
            [1, -1],
            [-1, 1],
            [0, 0],
        ],
        default=[np.nan, np.nan]
    ),
    index=res_factor.index,
    columns=["{x_code}", "{y_code}"]
)
"""

    else:
        raise ValueError('threshold_mode 只能填写 "absolute" 或 "quantile"')

    res_factor = res_factor.sort_index().shift(1)
    signal = eval(signal_exp.strip())
    signal_weight = get_signal_weight(signal)

    return signal, signal_weight




