# -*- coding: utf-8 -*-

import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from backtest_optimize import cal_signal_metric, get_signal_weight, get_security_type
from itertools import combinations
from statsmodels.tsa.stattools import adfuller, coint

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


security_type_list = ["fund", "stock", "future_all", "option_c_all", "option_p_all"]



class ______价差配对类_____():
    pass

def get_adf_pvalue(series, min_observations=60):
    clean_series = (
        pd.Series(series)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if len(clean_series) < min_observations:
        return np.nan

    try:
        return float(adfuller(clean_series, autolag="AIC")[1])
    except (ValueError, np.linalg.LinAlgError):
        return np.nan


def get_i1_diagnostics(price_series, alpha=0.05, min_observations=60):
    clean_price = pd.Series(price_series).where(
        pd.Series(price_series) > 0
    )
    log_price = np.log(clean_price)
    log_return = log_price.diff()

    price_adf_pvalue = get_adf_pvalue(
        log_price,
        min_observations=min_observations,
    )
    return_adf_pvalue = get_adf_pvalue(
        log_return,
        min_observations=min_observations,
    )

    is_i1 = (
        pd.notna(price_adf_pvalue)
        and pd.notna(return_adf_pvalue)
        and price_adf_pvalue >= alpha
        and return_adf_pvalue < alpha
    )

    return {
        "price_adf_pvalue": price_adf_pvalue,
        "return_adf_pvalue": return_adf_pvalue,
        "is_i1": is_i1,
    }

def select_pair_by_correlation(
    price_table,
    candidate_codes,
    correlation_start,
    correlation_end,
    min_observations=60,
    min_correlation=0.70,
    adf_alpha=0.05,
    cointegration_alpha=0.05,
):
    """从候选标的中，以筛选期的对数收益率相关系数选出最相关的一对。"""
    if candidate_codes is None or len(candidate_codes) < 2:
        raise ValueError("candidate_codes 至少需要填写两个候选标的。")

    candidate_codes = list(dict.fromkeys(candidate_codes))
    price_table = price_table.copy()
    price_table.index = pd.to_datetime(price_table.index)

    missing_codes = [
        code for code in candidate_codes
        if code not in price_table.columns
    ]
    if missing_codes:
        raise ValueError(
            f"候选标的未出现在价格数据中：{missing_codes}。"
            f"实际列为：{price_table.columns.tolist()}"
        )

    if correlation_start is None or correlation_end is None:
        raise ValueError("必须填写 correlation_start 和 correlation_end。")

    correlation_start = pd.Timestamp(correlation_start)
    correlation_end = pd.Timestamp(correlation_end)

    if correlation_start > correlation_end:
        raise ValueError("correlation_start 不能晚于 correlation_end。")

    sample_prices = price_table.loc[
        (price_table.index >= correlation_start)
        & (price_table.index <= correlation_end),
        candidate_codes,
    ]

    if sample_prices.empty:
        raise ValueError(
            "相关性筛选期内没有价格数据。请检查数据库是否包含 "
            f"{correlation_start.date()} 至 {correlation_end.date()} 的历史数据。"
        )

    valid_pairs = []
    for x_code, y_code in combinations(candidate_codes, 2):
        pair_prices = sample_prices[[x_code, y_code]].dropna()

        if len(pair_prices) < min_observations:
            continue

        x_i1 = get_i1_diagnostics(
            pair_prices[x_code],
            alpha=adf_alpha,
            min_observations=min_observations,
        )
        y_i1 = get_i1_diagnostics(
            pair_prices[y_code],
            alpha=adf_alpha,
            min_observations=min_observations,
        )

        if not (x_i1["is_i1"] and y_i1["is_i1"]):
            print(
                f"I(1)未通过：{x_code}/{y_code}；"
                f"X价格ADF={x_i1['price_adf_pvalue']:.4f}，"
                f"X收益率ADF={x_i1['return_adf_pvalue']:.4f}；"
                f"Y价格ADF={y_i1['price_adf_pvalue']:.4f}，"
                f"Y收益率ADF={y_i1['return_adf_pvalue']:.4f}"
            )
            continue

        cointegration = get_cointegration_diagnostics(
            pair_prices[x_code],
            pair_prices[y_code],
            adf_alpha=adf_alpha,
            cointegration_alpha=cointegration_alpha,
            min_observations=min_observations,
        )
        if not cointegration["is_cointegrated"]:
            print(
                f"协整未通过：{x_code}/{y_code}；"
                f"E-G p值={cointegration['eg_pvalue']:.4f}，"
                f"残差ADF p值={cointegration['resid_adf_pvalue']:.4f}"
            )
            continue

        pair_returns = np.log(pair_prices).diff().dropna()

        if len(pair_returns) < min_observations:
            continue

        correlation = pair_returns[x_code].corr(pair_returns[y_code])

        if pd.notna(correlation) and correlation >= min_correlation:
            valid_pairs.append(
                (x_code, y_code, float(correlation), len(pair_returns))
            )

    if not valid_pairs:
        print("没有候选对同时通过 I(1)、E-G 协整和相关性筛选，本轮不交易。")
        return None

    return max(valid_pairs, key=lambda item: item[2])

def get_cointegration_diagnostics(
    x_price,
    y_price,
    adf_alpha=0.05,
    cointegration_alpha=0.05,
    min_observations=60,
):
    pair_prices = pd.concat(
        [
            pd.Series(x_price, name="x"),
            pd.Series(y_price, name="y"),
        ],
        axis=1,
    )
    pair_prices = pair_prices.replace([np.inf, -np.inf], np.nan).dropna()
    pair_prices = pair_prices[
        (pair_prices["x"] > 0)
        & (pair_prices["y"] > 0)
    ]

    if len(pair_prices) < min_observations:
        return {
            "eg_pvalue": np.nan,
            "resid_adf_pvalue": np.nan,
            "beta": np.nan,
            "is_cointegrated": False,
        }

    log_x = np.log(pair_prices["x"])
    log_y = np.log(pair_prices["y"])

    try:
        _, eg_pvalue, _ = coint(log_y, log_x, trend="c")

        x_matrix = np.column_stack(
            [np.ones(len(log_x)), log_x.to_numpy()]
        )
        alpha_value, beta = np.linalg.lstsq(
            x_matrix,
            log_y.to_numpy(),
            rcond=None,
        )[0]

        residual = log_y - alpha_value - beta * log_x
        resid_adf_pvalue = get_adf_pvalue(
            residual,
            min_observations=min_observations,
        )

    except (ValueError, np.linalg.LinAlgError):
        eg_pvalue = np.nan
        resid_adf_pvalue = np.nan
        beta = np.nan

    is_cointegrated = (
            pd.notna(eg_pvalue)
            and pd.notna(resid_adf_pvalue)
            and eg_pvalue < cointegration_alpha
            and resid_adf_pvalue < adf_alpha
    )

    return {
        "eg_pvalue": eg_pvalue,
        "resid_adf_pvalue": resid_adf_pvalue,
        "beta": beta,
        "is_cointegrated": is_cointegrated,
    }

def resid(
    df,
    window=60,
    adf_alpha=0.05,
    cointegration_alpha=0.05,
    require_rolling_cointegration=True,
):
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
    res_factor["eg_pvalue"] = np.nan
    res_factor["resid_adf_pvalue"] = np.nan
    res_factor["cointegration_pass"] = False

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
        try:
            eg_pvalue = coint(y_values, x_values)[1]
            resid_adf_pvalue = adfuller(resid_series, autolag="AIC")[1]
        except (ValueError, np.linalg.LinAlgError):
            eg_pvalue = np.nan
            resid_adf_pvalue = np.nan

        cointegration_pass = (
                not require_rolling_cointegration
                or (
                        pd.notna(eg_pvalue)
                        and pd.notna(resid_adf_pvalue)
                        and eg_pvalue < cointegration_alpha
                        and resid_adf_pvalue < adf_alpha
                )
        )

        current_date = df.index[end_idx]

        res_factor.loc[current_date, "alpha"] = alpha
        res_factor.loc[current_date, "beta"] = beta
        res_factor.loc[current_date, "resid"] = resid_series[-1]
        res_factor.loc[current_date, "resid_mean"] = resid_series.mean()
        res_factor.loc[current_date, "resid_std"] = resid_series.std(ddof=1)
        res_factor.loc[current_date, "eg_pvalue"] = eg_pvalue
        res_factor.loc[current_date, "resid_adf_pvalue"] = resid_adf_pvalue
        res_factor.loc[current_date, "cointegration_pass"] = cointegration_pass

    return res_factor



def resid_signal(
    df,
    window=60,
    X=2,
    stop_loss_X=3,
    threshold_mode="absolute",
    candidate_codes=None,
    correlation_start=None,
    correlation_end=None,
    correlation_min_observations=60,
    correlation_min_value=0.70,
    adf_alpha=0.05,
    cointegration_alpha=0.05,
    require_rolling_cointegration=True,
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

    candidate_codes = (
        candidate_codes
        if candidate_codes is not None
        else df_dataTrade.columns.tolist()
    )

    selection_result = select_pair_by_correlation(
        price_table=df_dataTrade,
        candidate_codes=candidate_codes,
        correlation_start=correlation_start,
        correlation_end=correlation_end,
        min_observations=correlation_min_observations,
        min_correlation=correlation_min_value,
        adf_alpha=adf_alpha,
        cointegration_alpha=cointegration_alpha,
    )

    if selection_result is None:
        print("本轮没有通过统计筛选的品种对，输出全 0 信号。")

        signal = pd.DataFrame(
            0.0,
            index=df_dataTrade.index,
            columns=candidate_codes,
        )
        signal_weight = pd.DataFrame(
            0.0,
            index=df_dataTrade.index,
            columns=candidate_codes,
        )

        return signal, signal_weight

    x_code, y_code, correlation, observation_count = selection_result

    print(
        f"相关性筛选结果：{x_code} 与 {y_code}；"
        f"对数收益率相关系数={correlation:.4f}；"
        f"有效样本数={observation_count}"
    )

    df_dataTrade = df_dataTrade[[x_code, y_code]]
    res_factor = resid(
        df_dataTrade.copy(),
        window=window,
        adf_alpha=adf_alpha,
        cointegration_alpha=cointegration_alpha,
        require_rolling_cointegration=require_rolling_cointegration,
    )

    if threshold_mode != "absolute":
        raise ValueError('当前研报复现只支持 threshold_mode="absolute"。')

    res_factor = res_factor.sort_index().shift(1)

    signal = pd.DataFrame(
        0.0,
        index=res_factor.index,
        columns=[x_code, y_code],
    )

    position = 0
    previous_z_score = np.nan

    for current_date, row in res_factor.iterrows():
        residual_std = row["resid_std"]
        if pd.isna(residual_std) or residual_std <= 0:
            position = 0
            previous_z_score = np.nan
            continue

        z_score = (row["resid"] - row["resid_mean"]) / residual_std
        cointegration_pass = row["cointegration_pass"]

        if (
                pd.isna(z_score)
                or (
                require_rolling_cointegration
                and (
                        pd.isna(cointegration_pass)
                        or not bool(cointegration_pass)
                )
        )
        ):
            position = 0
            previous_z_score = np.nan
            continue

        if position == 0:
            upper_crossed = (
                    pd.notna(previous_z_score)
                    and previous_z_score <= X
                    and z_score > X
                    and z_score < stop_loss_X
            )
            lower_crossed = (
                    pd.notna(previous_z_score)
                    and previous_z_score >= -X
                    and z_score < -X
                    and z_score > -stop_loss_X
            )

            if upper_crossed:
                position = 1
            elif lower_crossed:
                position = -1

        elif abs(z_score) <= X or abs(z_score) >= stop_loss_X:
            position = 0

        if position == 1:
            signal.loc[current_date] = [1.0, -1.0]
        elif position == -1:
            signal.loc[current_date] = [-1.0, 1.0]

        previous_z_score = z_score

        signal_weight = get_signal_weight(signal)

    return signal, signal_weight



