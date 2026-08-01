# -*- coding: utf-8 -*-

import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from backtest_optimize import cal_signal_metric, get_signal_weight, get_security_type
from statsmodels.tsa.stattools import adfuller, coint
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


security_type_list = ["fund", "stock", "future_all", "option_c_all", "option_p_all"]



class ______价差配对类_____():
    pass


# 1. 安全执行 ADF 检验
def _safe_adf_p_value(series, min_observations=60):
    """
    清洗输入序列并返回 ADF 检验的 p 值。

    p 值越小，越支持“序列平稳”的判断。
    """
    # 1.1 将输入统一转换为浮点型 Series。
    clean_series = (
        pd.Series(series)
        .astype(float)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    # 1.2 样本不足或所有数值完全相同时，不能执行 ADF 检验。
    if (
            len(clean_series) < min_observations
            or clean_series.nunique() <= 1
    ):
        return np.nan

    # 1.3 执行 ADF 检验，返回其中的 p 值。
    try:
        return float(
            adfuller(clean_series, autolag="AIC")[1]
        )

    # 1.4 遇到无效数据或矩阵计算失败时，返回空值。
    except (ValueError, np.linalg.LinAlgError):
        return np.nan


# 2. 检查单个价格序列是否为一阶单整序列 I(1)
def _is_first_order_integrated(
        price_series,
        p_value_threshold=0.01,
        min_observations=60,
):
    """
    检查价格序列是否满足：

    1. 对数价格不平稳；
    2. 对数价格的一阶差分平稳。

    同时满足以上条件时，将其判断为 I(1) 序列。
    """
    # 2.1 转换为浮点数，只保留大于 0 的有效价格。
    clean_price = (
        pd.Series(price_series)
        .astype(float)
        .where(lambda value: value > 0)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    # 2.2 计算对数价格。
    log_price = np.log(clean_price)

    # 2.3 对数价格的一阶差分，即对数收益率。
    log_return = log_price.diff().dropna()

    # 2.4 检验对数价格是否平稳。
    level_p_value = _safe_adf_p_value(
        log_price,
        min_observations=min_observations,
    )

    # 2.5 差分后会减少一个样本，因此最低样本数相应减 1。
    return_p_value = _safe_adf_p_value(
        log_return,
        min_observations=max(min_observations - 1, 1),
    )

    # 2.6 一阶单整判断：
    # 对数价格 p 值大于等于阈值，表示价格不平稳；
    # 对数收益率 p 值小于阈值，表示一阶差分平稳。
    is_i1 = (
            pd.notna(level_p_value)
            and pd.notna(return_p_value)
            and level_p_value >= p_value_threshold
            and return_p_value < p_value_threshold
    )

    # 2.7 返回判断结果和两个 p 值，便于日志记录和检查。
    return {
        "is_i1": is_i1,
        "level_adf_p_value": level_p_value,
        "return_adf_p_value": return_p_value,
    }


# 3. 对两个价格序列进行 E-G 协整检验和 OLS 回归
def _get_cointegration_diagnostics(
        x_price,
        y_price,
        adf_p_value_threshold=0.01,
        engle_granger_p_value_threshold=0.01,
        min_observations=60,
        run_cointegration_tests=True,
):
    """
    计算并返回：

    1. E-G 协整检验 p 值；
    2. OLS 回归的 alpha 和 beta；
    3. 回归残差的 ADF p 值；
    4. 品种对是否通过协整检验。
    """
    # 3.1 按索引对齐 X、Y 两个价格序列。
    pair_price = pd.concat(
        [
            pd.Series(x_price, name="x"),
            pd.Series(y_price, name="y"),
        ],
        axis=1,
    )

    # 3.2 转换为浮点数，并删除无穷值和空值。
    pair_price = (
        pair_price
        .astype(float)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    # 3.3 对数价格要求原始价格必须大于 0。
    pair_price = pair_price[
        (pair_price["x"] > 0)
        & (pair_price["y"] > 0)
    ]

    # 3.4 有效样本少于窗口长度时，不进行协整检验。
    if len(pair_price) < min_observations:
        return {
            "cointegration_pass": False,
            "engle_granger_p_value": np.nan,
            "residual_adf_p_value": np.nan,
            "alpha": np.nan,
            "beta": np.nan,
        }

    # 3.5 分别计算 X、Y 的对数价格。
    log_x = np.log(pair_price["x"])
    log_y = np.log(pair_price["y"])

    try:
        # 3.6 候选筛选或严格模式下执行 E-G 协整检验。
        # 研报交易模式下跳过每日重复检验，以缩短运行时间。
        if run_cointegration_tests:
            engle_granger_p_value = float(
                coint(log_y, log_x, trend="c")[1]
            )
        else:
            engle_granger_p_value = np.nan

        # 3.7 构造包含常数项的 OLS 自变量矩阵。

        # 3.7 构造包含常数项的 OLS 自变量矩阵。
        x_matrix = np.column_stack(
            [
                np.ones(len(log_x)),
                log_x.to_numpy(),
            ]
        )

        # 3.8 估计回归方程：
        # log(Y) = alpha + beta * log(X) + residual。
        alpha, beta = np.linalg.lstsq(
            x_matrix,
            log_y.to_numpy(),
            rcond=None,
        )[0]

        # 3.9 根据 OLS 参数计算残差序列。
        residual = (
                log_y
                - alpha
                - beta * log_x
        )

        # 3.10 候选筛选或严格模式下执行残差 ADF 检验。
        # 研报交易模式下保留滚动 OLS，但跳过每日重复检验。
        if run_cointegration_tests:
            residual_adf_p_value = _safe_adf_p_value(
                residual,
                min_observations=min_observations,
            )
        else:
            residual_adf_p_value = np.nan

    # 3.11 检验或矩阵计算失败时，将诊断结果设为空值。
    except (ValueError, np.linalg.LinAlgError):
        engle_granger_p_value = np.nan
        residual_adf_p_value = np.nan
        alpha = np.nan
        beta = np.nan

        # 3.12 执行统计检验时，E-G 和残差 ADF 必须同时通过。
    if run_cointegration_tests:
        cointegration_pass = (
                pd.notna(engle_granger_p_value)
                and pd.notna(residual_adf_p_value)
                and engle_granger_p_value
                < engle_granger_p_value_threshold
                and residual_adf_p_value
                < adf_p_value_threshold
        )
    else:
        # 研报交易模式已在候选期完成协整筛选，
        # 滚动阶段只更新 OLS 参数，不再使用每日协整结果拦截交易。
        cointegration_pass = True

    # 3.13 返回完整诊断结果，供品种筛选和滚动回归使用。
    return {
        "cointegration_pass": cointegration_pass,
        "engle_granger_p_value": engle_granger_p_value,
        "residual_adf_p_value": residual_adf_p_value,
        "alpha": (
            float(alpha)
            if pd.notna(alpha)
            else np.nan
        ),
        "beta": (
            float(beta)
            if pd.notna(beta)
            else np.nan
        ),
    }

# 4. 从配置给出的候选品种对中选择有效交易组合
def _select_candidate_pair(
        price_table,
        candidate_pairs,
        correlation_start,
        correlation_end,
        adf_p_value_threshold=0.01,
        engle_granger_p_value_threshold=0.01,
        min_observations=60,
):
    """
    在指定历史区间内依次检查候选品种对：

    1. 两个价格序列是否均为 I(1)；
    2. 两个价格序列是否通过 E-G 协整检验；
    3. 计算两个品种的对数收益率相关系数；
    4. 从通过检验的组合中选择相关系数最高的一对。
    """
    # 4.1 candidate_pairs 必须至少包含一个候选组合。
    if not candidate_pairs:
        raise ValueError(
            "candidate_pairs 至少需要配置一个候选品种对。"
        )

    # 4.2 复制价格表，避免修改框架传入的原始数据。
    price_table = price_table.copy()
    price_table.index = pd.to_datetime(price_table.index)
    price_table = price_table.sort_index()

    # 4.3 将配置中的筛选起止日期转换为时间类型。
    correlation_start = pd.Timestamp(correlation_start)
    correlation_end = pd.Timestamp(correlation_end)

    # 4.4 筛选开始日期不能晚于结束日期。
    if correlation_start > correlation_end:
        raise ValueError(
            "correlation_start 不能晚于 correlation_end。"
        )

    # 4.5 保存所有通过统计检验的候选组合。
    valid_pairs = []

    # 4.6 逐一检查 config.py 中配置的候选品种对。
    for candidate_pair in candidate_pairs:
        # 每个候选组合必须正好包含两个品种代码。
        if len(candidate_pair) != 2:
            raise ValueError(
                "candidate_pairs 中的每个组合必须包含两个品种代码。"
            )

        x_code, y_code = candidate_pair

        # 4.7 检查两个代码是否都存在于价格表中。
        missing_codes = [
            code
            for code in (x_code, y_code)
            if code not in price_table.columns
        ]

        if missing_codes:
            raise ValueError(
                "候选品种未出现在行情数据中：{}".format(
                    missing_codes
                )
            )

        # 4.8 截取相关性和协整关系的历史筛选区间。
        pair_price = price_table.loc[
            (price_table.index >= correlation_start)
            & (price_table.index <= correlation_end),
            [x_code, y_code],
        ].dropna()

        # 4.9 有效价格数量不足时，该组合不能参与筛选。
        if len(pair_price) < min_observations:
            print(
                "候选组合 {}/{} 样本不足：{} < {}".format(
                    x_code,
                    y_code,
                    len(pair_price),
                    min_observations,
                )
            )
            continue

        # 4.10 分别检查两个价格序列是否为 I(1)。
        x_i1_result = _is_first_order_integrated(
            pair_price[x_code],
            p_value_threshold=adf_p_value_threshold,
            min_observations=min_observations,
        )
        y_i1_result = _is_first_order_integrated(
            pair_price[y_code],
            p_value_threshold=adf_p_value_threshold,
            min_observations=min_observations,
        )

        # 4.11 任意一腿不是 I(1) 时，拒绝该组合。
        if not (
                x_i1_result["is_i1"]
                and y_i1_result["is_i1"]
        ):
            print(
                "候选组合 {}/{} 未通过 I(1) 检验。".format(
                    x_code,
                    y_code,
                )
            )
            continue

        # 4.12 执行 E-G 协整检验和残差 ADF 检验。
        cointegration_result = _get_cointegration_diagnostics(
            pair_price[x_code],
            pair_price[y_code],
            adf_p_value_threshold=adf_p_value_threshold,
            engle_granger_p_value_threshold=(
                engle_granger_p_value_threshold
            ),
            min_observations=min_observations,
        )

        # 4.13 协整检验失败时，不允许该组合参与交易。
        if not cointegration_result["cointegration_pass"]:
            print(
                "候选组合 {}/{} 未通过协整检验："
                "E-G p值={:.6f}，残差ADF p值={:.6f}".format(
                    x_code,
                    y_code,
                    cointegration_result[
                        "engle_granger_p_value"
                    ],
                    cointegration_result[
                        "residual_adf_p_value"
                    ],
                )
            )
            continue

        # 4.14 计算两个品种的对数收益率。
        pair_log_return = (
            np.log(pair_price[[x_code, y_code]])
            .diff()
            .dropna()
        )

        # 4.15 计算两个品种的收益率相关系数。
        correlation = pair_log_return[x_code].corr(
            pair_log_return[y_code]
        )

        if pd.isna(correlation):
            print(
                "候选组合 {}/{} 无法计算相关系数。".format(
                    x_code,
                    y_code,
                )
            )
            continue

        # 4.16 保存通过全部检查的候选组合和诊断结果。
        valid_pairs.append(
            {
                "x_code": x_code,
                "y_code": y_code,
                "correlation": float(correlation),
                "engle_granger_p_value": cointegration_result[
                    "engle_granger_p_value"
                ],
                "residual_adf_p_value": cointegration_result[
                    "residual_adf_p_value"
                ],
                "alpha": cointegration_result["alpha"],
                "beta": cointegration_result["beta"],
                "observation_count": len(pair_price),
            }
        )

    # 4.17 没有组合通过时返回 None，由主函数输出全 0 信号。
    if not valid_pairs:
        return None

    # 4.18 返回对数收益率相关系数最高的有效组合。
    return max(
        valid_pairs,
        key=lambda result: result["correlation"],
    )

# 5. 计算两个品种的滚动 OLS 回归残差
def _calculate_rolling_residuals(
        price_table,
        x_code,
        y_code,
        rolling_window=60,
        adf_p_value_threshold=0.01,
        engle_granger_p_value_threshold=0.01,
        require_rolling_cointegration=True,
):
    """
    使用最近 rolling_window 个交易日进行滚动 OLS 回归。

    回归公式：
        log(Y) = alpha + beta * log(X) + residual

    返回每日的 alpha、beta、残差、残差均值、标准差、
    z-score 和滚动协整检验结果。
    """
    # 5.1 滚动窗口至少需要两个样本。
    if rolling_window < 2:
        raise ValueError(
            "rolling_window 必须大于或等于 2。"
        )

    # 5.2 检查两腿代码是否都存在于价格表中。
    missing_codes = [
        code
        for code in (x_code, y_code)
        if code not in price_table.columns
    ]

    if missing_codes:
        raise ValueError(
            "滚动回归缺少行情列：{}".format(
                missing_codes
            )
        )

    # 5.3 复制并整理两腿价格，避免修改原始行情。
    pair_price = (
        price_table[[x_code, y_code]]
        .copy()
        .astype(float)
        .sort_index()
    )

    # 5.4 创建结果表，并保留两腿原始价格。
    rolling_result = pair_price.copy()

    # 5.5 初始化滚动回归和统计检验结果列。
    rolling_result["alpha"] = np.nan
    rolling_result["beta"] = np.nan
    rolling_result["residual"] = np.nan
    rolling_result["residual_mean"] = np.nan
    rolling_result["residual_std"] = np.nan
    rolling_result["z_score"] = np.nan
    rolling_result["engle_granger_p_value"] = np.nan
    rolling_result["residual_adf_p_value"] = np.nan
    rolling_result["cointegration_pass"] = False

    # 5.6 从第一个完整滚动窗口开始逐日计算。
    for end_position in range(
            rolling_window - 1,
            len(pair_price),
    ):
        # 5.7 截取截至当前日期的最近 rolling_window 条行情。
        window_price = pair_price.iloc[
            end_position - rolling_window + 1:
            end_position + 1
        ]

        # 5.8 删除空值和非正价格。
        window_price = (
            window_price
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )

        window_price = window_price[
            (window_price[x_code] > 0)
            & (window_price[y_code] > 0)
        ]

        # 5.9 窗口数据不完整时，当前日期不生成因子。
        if len(window_price) < rolling_window:
            continue

        # 5.10 对当前窗口执行 OLS 和协整诊断。
        diagnostics = _get_cointegration_diagnostics(
            window_price[x_code],
            window_price[y_code],
            adf_p_value_threshold=(
                adf_p_value_threshold
            ),
            engle_granger_p_value_threshold=(
                engle_granger_p_value_threshold
            ),
            min_observations=rolling_window,
            run_cointegration_tests=(
                require_rolling_cointegration
            ),
        )

        alpha = diagnostics["alpha"]
        beta = diagnostics["beta"]

        # 5.11 OLS 参数无效时，跳过当前日期。
        if pd.isna(alpha) or pd.isna(beta):
            continue

        # 5.12 使用当期 OLS 参数计算整个窗口的残差序列。
        log_x = np.log(window_price[x_code])
        log_y = np.log(window_price[y_code])

        residual_series = (
                log_y
                - alpha
                - beta * log_x
        )

        # 5.13 计算窗口内残差的均值和样本标准差。
        residual_mean = residual_series.mean()
        residual_std = residual_series.std(ddof=1)

        # 5.14 标准差无效或等于零时，不能计算 z-score。
        if (
                pd.isna(residual_std)
                or residual_std <= 0
        ):
            continue

        # 5.15 当前日期使用窗口最后一个残差值。
        current_residual = residual_series.iloc[-1]

        # 5.16 将当前残差标准化为 z-score。
        z_score = (
                current_residual
                - residual_mean
        ) / residual_std

        current_date = pair_price.index[end_position]

        # 5.17 保存当前日期的全部滚动结果。
        rolling_result.loc[current_date, "alpha"] = alpha
        rolling_result.loc[current_date, "beta"] = beta
        rolling_result.loc[
            current_date,
            "residual",
        ] = current_residual
        rolling_result.loc[
            current_date,
            "residual_mean",
        ] = residual_mean
        rolling_result.loc[
            current_date,
            "residual_std",
        ] = residual_std
        rolling_result.loc[
            current_date,
            "z_score",
        ] = z_score
        rolling_result.loc[
            current_date,
            "engle_granger_p_value",
        ] = diagnostics["engle_granger_p_value"]
        rolling_result.loc[
            current_date,
            "residual_adf_p_value",
        ] = diagnostics["residual_adf_p_value"]
        rolling_result.loc[
            current_date,
            "cointegration_pass",
        ] = diagnostics["cointegration_pass"]

    # 5.18 返回完整滚动因子表。
    return rolling_result

# 6. 商品期货跨品种套利主函数
def commodity_cross_variety_arbitrage_signal(
        df,
        rolling_window=60,
        entry_sigma=2.0,
        exit_sigma=0.0,
        stop_loss_sigma=3.0,
        candidate_pairs=None,
        correlation_start=None,
        correlation_end=None,
        adf_p_value_threshold=0.01,
        engle_granger_p_value_threshold=0.01,
        execution_delay=1,
        require_rolling_cointegration=False,
        backtest_trading_mode="backtest",
        **kwargs
):
    """
    商品期货跨品种套利信号。

    执行流程：
    1. 整理两腿收盘价；
    2. 执行 I(1)、E-G 协整和相关性筛选；
    3. 使用 60 日滚动 OLS 计算残差 z-score；
    4. 残差上穿或下穿正负 2 倍标准差时开仓；
    5. 残差回归均值或达到正负 3 倍标准差时平仓；
    6. 将信号延迟一个交易日执行。
    """
    # 6.1 检查框架传入的数据类型。
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df 必须是 pandas DataFrame。")

    # 6.2 检查生成因子所必需的字段。
    required_columns = {"ts_code", "close"}
    missing_columns = required_columns.difference(df.columns)

    if missing_columns:
        raise ValueError(
            "原始行情缺少字段：{}".format(
                sorted(missing_columns)
            )
        )

    # 6.3 检查滚动窗口参数。
    if (
            not isinstance(rolling_window, (int, np.integer))
            or rolling_window < 2
    ):
        raise ValueError(
            "rolling_window 必须是大于或等于 2 的整数。"
        )

    # 6.4 将阈值参数转换为浮点数。
    entry_sigma = float(entry_sigma)
    exit_sigma = float(exit_sigma)
    stop_loss_sigma = float(stop_loss_sigma)

    # 6.5 阈值必须满足：0 <= 平仓线 < 开仓线 < 止损线。
    if not (
            0 <= exit_sigma
            < entry_sigma
            < stop_loss_sigma
    ):
        raise ValueError(
            "阈值必须满足："
            "0 <= exit_sigma < entry_sigma < stop_loss_sigma。"
        )

    # 6.6 T+1 延迟必须使用非负整数。
    if (
            not isinstance(execution_delay, (int, np.integer))
            or execution_delay < 0
    ):
        raise ValueError(
            "execution_delay 必须是大于或等于 0 的整数。"
        )

    # 6.7 必须配置候选品种筛选区间。
    if correlation_start is None or correlation_end is None:
        raise ValueError(
            "必须配置 correlation_start 和 correlation_end。"
        )

    correlation_end_timestamp = pd.Timestamp(
        correlation_end
    )

    # 6.8 将原始长表转换为“日期 × 品种”的收盘价表。
    price_table = pd.pivot_table(
        df,
        index=df.index,
        columns="ts_code",
        values="close",
        aggfunc="mean",
    ).sort_index()

    # 6.9 保持品种列顺序与原始数据首次出现顺序一致。
    security_codes = (
        df["ts_code"]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    price_table = price_table.reindex(
        columns=security_codes
    )
    price_table.index = pd.to_datetime(
        price_table.index
    )

    # 6.10 创建默认全 0 信号表。
    signal = pd.DataFrame(
        0.0,
        index=price_table.index,
        columns=price_table.columns,
    )

    # 6.11 对 config.py 中的候选品种对执行统计筛选。
    selected_pair = _select_candidate_pair(
        price_table=price_table,
        candidate_pairs=candidate_pairs,
        correlation_start=correlation_start,
        correlation_end=correlation_end,
        adf_p_value_threshold=(
            adf_p_value_threshold
        ),
        engle_granger_p_value_threshold=(
            engle_granger_p_value_threshold
        ),
        min_observations=rolling_window,
    )

    # 6.12 没有品种对通过筛选时，保持全 0 信号。
    if selected_pair is None:
        print(
            "没有候选品种对同时通过 "
            "I(1)、E-G 协整和有效数据检查，本轮不交易。"
        )

        # 没有品种对通过筛选时，返回全 0 信号及对应权重。
        signal_weight = get_signal_weight(signal)

        return signal, signal_weight

    # 6.13 读取筛选出的两腿代码。
    x_code = selected_pair["x_code"]
    y_code = selected_pair["y_code"]

    # 6.14 输出筛选结果，便于检查和保存回测依据。
    print(
        "候选品种筛选结果：{} 与 {}；"
        "相关系数={:.6f}；"
        "E-G p值={:.6f}；"
        "残差ADF p值={:.6f}；"
        "有效样本数={}".format(
            x_code,
            y_code,
            selected_pair["correlation"],
            selected_pair[
                "engle_granger_p_value"
            ],
            selected_pair[
                "residual_adf_p_value"
            ],
            selected_pair["observation_count"],
        )
    )

    # 6.15 计算两腿的滚动 OLS 残差和 z-score。
    rolling_result = _calculate_rolling_residuals(
        price_table=price_table,
        x_code=x_code,
        y_code=y_code,
        rolling_window=rolling_window,
        adf_p_value_threshold=(
            adf_p_value_threshold
        ),
        engle_granger_p_value_threshold=(
            engle_granger_p_value_threshold
        ),
        require_rolling_cointegration=(
            require_rolling_cointegration
        ),
    )

    # 6.16 position 表示当前价差仓位状态：
    # 0 为空仓，1 为做多 X/做空 Y，-1 为做空 X/做多 Y。
    position = 0

    # 6.17 保存前一个有效交易日的 z-score，用于判断穿越。
    previous_z_score = np.nan

    # 6.18 按日期逐日生成状态机信号。
    for current_date, factor_row in rolling_result.iterrows():
        # 统计筛选期只用于选品种，不允许产生交易信号。
        if current_date <= correlation_end_timestamp:
            position = 0
            previous_z_score = np.nan
            continue

        z_score = factor_row["z_score"]
        cointegration_pass = factor_row[
            "cointegration_pass"
        ]

        # 6.19 研报模式只在 z-score 无效时强制空仓。
        # 当配置主动开启严格模式时，滚动协整失败也会强制空仓。
        rolling_cointegration_failed = (
                require_rolling_cointegration
                and (
                        pd.isna(cointegration_pass)
                        or not bool(cointegration_pass)
                )
        )

        if (
                pd.isna(z_score)
                or rolling_cointegration_failed
        ):
            position = 0
            previous_z_score = np.nan
            continue

        # 6.20 空仓状态下，只在残差刚刚穿越开仓线时开仓。
        if position == 0:
            # 残差向上穿越开仓线：
            # Y 相对高估，因此做多 X、做空 Y。
            upper_crossed = (
                    pd.notna(previous_z_score)
                    and previous_z_score < entry_sigma
                    and z_score >= entry_sigma
                    and z_score < stop_loss_sigma
            )

            # 残差向下穿越开仓线：
            # Y 相对低估，因此做空 X、做多 Y。
            lower_crossed = (
                    pd.notna(previous_z_score)
                    and previous_z_score > -entry_sigma
                    and z_score <= -entry_sigma
                    and z_score > -stop_loss_sigma
            )

            if upper_crossed:
                position = 1
            elif lower_crossed:
                position = -1

        # 6.21 持仓状态下检查均值平仓和止损平仓。
        else:
            # 残差绝对值达到止损线时立即平仓。
            stop_loss_triggered = (
                    abs(z_score) >= stop_loss_sigma
            )

            # 上方开仓后，残差回落到平仓线时平仓。
            upper_position_exit = (
                    position == 1
                    and z_score <= exit_sigma
            )

            # 下方开仓后，残差回升到平仓线时平仓。
            lower_position_exit = (
                    position == -1
                    and z_score >= -exit_sigma
            )

            if (
                    stop_loss_triggered
                    or upper_position_exit
                    or lower_position_exit
            ):
                position = 0

        # 6.22 根据当前仓位状态写入两腿方向。
        if position == 1:
            signal.loc[current_date, x_code] = 1.0
            signal.loc[current_date, y_code] = -1.0

        elif position == -1:
            signal.loc[current_date, x_code] = -1.0
            signal.loc[current_date, y_code] = 1.0

        # 6.23 保存当前 z-score，供下一交易日判断穿越。
        previous_z_score = z_score

    # 6.24 将信号整体后移 execution_delay 个交易日。
    # config.py 中 execution_delay=1，即执行 T+1。
    if execution_delay > 0:
        signal = (
            signal
            .sort_index()
            .shift(execution_delay)
            .fillna(0.0)
        )

    # 6.25 统计最终可执行信号，便于确认策略是否真正产生交易机会。
    active_signal_mask = signal.ne(0).any(axis=1)
    active_signal_dates = signal.index[active_signal_mask]

    previous_x_signal = (
        signal[x_code]
        .shift(1)
        .fillna(0.0)
    )
    entry_count = int(
        (
                (signal[x_code] != 0)
                & (previous_x_signal == 0)
        ).sum()
    )
    exit_count = int(
        (
                (signal[x_code] == 0)
                & (previous_x_signal != 0)
        ).sum()
    )

    if len(active_signal_dates) > 0:
        print(
            "信号生成结果：非零持仓信号天数={}；"
            "开仓次数={}；平仓次数={}；"
            "首次信号日期={}；末次信号日期={}".format(
                len(active_signal_dates),
                entry_count,
                exit_count,
                active_signal_dates[0],
                active_signal_dates[-1],
            )
        )
    else:
        print(
            "信号生成结果：全部为0；"
            "请检查筛选条件、z-score和状态机。"
        )

    # 6.25 使用框架通用函数生成信号权重。
    signal_weight = get_signal_weight(signal)

    # 6.26 当前未开启参数寻优，只返回信号和权重。
    # 如果返回第三个空指标，pipeline 会误把信号截成第一行。
    return signal, signal_weight


def calculate_spread(df, window=60):     # ！！！范例，使用时需删除！！！
    """
        出处：https://mp.weixin.qq.com/xxxxxxxxxxxxxxxxxx
        价差
    :param df, DataFrame: 计算的原始数据,索引需要是日期；
    :param window, int: 窗长
    :return: df, DataFrame: 因子值；
    """
    # 2. 计算价差
    def normalize_prices(df, window=60):
        # 1. 计算滚动标准化价格
        normalized = pd.DataFrame()
        # 对每一列做标准化处理；
        for col in df.columns:
            # 计算滚动均值和标准差
            # rolling_mean = df[col].rolling(window=window).mean()
            # rolling_std = df[col].rolling(window=window).std()
            rolling_mean = df[col].fillna(0).replace([np.inf, -np.inf], 0).rolling(window=window).mean()    # 计算滚动窗长内的平均值
            rolling_std = df[col].fillna(0).replace([np.inf, -np.inf], 0).rolling(window=window).std()    # 计算滚动窗长内的标准差
            # 标准化价格
            normalized[col] = (df[col] - rolling_mean) / rolling_std

        # return normalized.dropna()  # 删除 NaN 值
        return normalized

    # df['price_diff'] = normalize_prices(df.iloc[:,[0]], window) - normalize_prices(df.iloc[:,[1]], window)  # 计算资产价格差
    # df['price_diff'] = normalize_prices(df.iloc[:,[0]], window).values - normalize_prices(df.iloc[:,[1]], window).values  # 计算资产价格差
    df['price_diff'] = normalize_prices(df.iloc[:,[0]].ffill(), window).values - normalize_prices(df.iloc[:,[1]].ffill(), window).values  # 计算资产价格差
    # df['mean_diff'] = df['price_diff'].mean()  # 价格差的均值
    # df['std_diff'] = df['price_diff'].std()  # 标准差
    df['mean_diff'] = df['price_diff'].replace([np.inf, -np.inf], 0).mean()  # 价格差的均值
    df['std_diff'] = df['price_diff'].replace([np.inf, -np.inf], 0).std()  # 标准差

    return df


def calculate_spread_signal(df, window=60, backtest_trading_mode='backtest', **kwargs):     # ！！！范例，使用时需删除！！！
    """
        出处：https://mp.weixin.qq.com/xxxxxxxxxxxxxxx
        价差
    :param df, DataFrame: 计算的原始数据,索引需要是日期；
    :param window, int: 窗长
    :param backtest_trading_mode, str: 回测、实盘交易模式
    :return: signal, DataFrame: 基于套利策略计算得到的交易数据和信号；
             signal_weight, DataFrame: 基于套利策略计算得到的交易信号对应权重；
             res_optimize_metric, list: 基于寻优框架得到的寻优结果
    """
    # 获取套利框架所需全量原始因子数据，该变量数据不能修改，需要完整传入套利框架中
    dataFactorSrc = df.copy()
    # 转透视表：行索引为时间，列索引为标的；如果行、列有重复值，会聚合，默认aggfunc='mean';
    df_dataTrade = pd.pivot_table(df, index=df.index, columns='ts_code', values='close').sort_index()    # , dropna=False
    df_dataTrade = df_dataTrade.reindex(columns=df['ts_code'].dropna().drop_duplicates().tolist())      # 补齐行索引；

    # 不限品种，所有品种总标的数量为2
    security_type_dict = get_security_type(df['ts_code'].dropna().drop_duplicates().tolist())
    if not (sum(len(security_type_dict.get(k, []) or []) for k in security_type_list) == 2):
        print("error：不满足：只统计 security_type_list 中的品种，这些品种的标的总数必须是 2；security_type_list 之外的品种不限制")
        return pd.DataFrame()

    # 调用rsj因子，生成交易信号
    res_factor = calculate_spread(df_dataTrade.copy(), window=window)
    res_factor = res_factor.sort_index().shift(1)   # 将因子结果向后一个时间移动，防止出现未来数据。
    # 基于因子值生成信号的可执行的字符串表达式
    signal_exp = """pd.DataFrame(
        np.select([
                ((res_factor['price_diff'] > res_factor['mean_diff']) & (abs(res_factor['price_diff']-res_factor['mean_diff']) > sig_coef_A * res_factor['std_diff']) & (abs(res_factor['price_diff']-res_factor['mean_diff']) < sig_coef_B * res_factor['std_diff'])).to_numpy()[:, None],
                ((res_factor['price_diff'] < res_factor['mean_diff']) & (abs(res_factor['price_diff']-res_factor['mean_diff']) > sig_coef_A * res_factor['std_diff']) & (abs(res_factor['price_diff']-res_factor['mean_diff']) < sig_coef_B * res_factor['std_diff'])).to_numpy()[:, None],
                ((abs(res_factor['price_diff']-res_factor['mean_diff']) < sig_coef_C * res_factor['std_diff']) | (abs(res_factor['price_diff']-res_factor['mean_diff']) > sig_coef_D * res_factor['std_diff'])).to_numpy()[:, None],
            ], [[-1, 1], [1, -1], [0, 0]],
            default=[np.nan, np.nan]
        ),
        index=res_factor.index,
        # columns=df_dataTrade.columns
        columns=[c for c in res_factor.columns if c in df_dataTrade.columns]
    )"""

    if (not backtest_trading_mode or ('backtest' in backtest_trading_mode if isinstance(backtest_trading_mode, str) else any(isinstance(x, str) and 'backtest' in x for x in backtest_trading_mode) if isinstance(backtest_trading_mode, (list, tuple, set)) else False)):
        signal, res_optimize_metric = cal_signal_metric(res_factor=res_factor, dataFactorSrc=dataFactorSrc, signal_exp=signal_exp, **kwargs)   # 绩效绩效评价
    else:
        signal, res_optimize_metric = eval(signal_exp.strip()), []      # 非回测模式，不执行绩效评级计算，直接计算信号值

    signal_weight = get_signal_weight(signal)   # 获取信号权重

    # signal = signal.sort_index().shift(1)   # 将信号结果向后一个时间移动，防止出现未来数据。
    # signal_weight = signal_weight.sort_index().shift(1)   # 将信号权重结果向后一个时间移动，防止出现未来数据。

    return signal, signal_weight, res_optimize_metric




class ______期权_价差_特有_____():
    pass




def Arbitrage(df, n=2):     # ！！！范例，使用时需删除！！！
    """
        出处：《配对交易类-2_xxx》
        出处：《期权-对冲类-期权与期权组合的对冲-An-xxxxxxxxxxxxxxxx》
        功能：通过多空组合的期权资产组合的差值比较，释放交易信号
    :param df, Series: 计算的原始数据，索引需要是日期；
    :param n: int: 发出交易信号的阈值
    :return: signal, DataFrame: 交易信号；
    """
    # df = df.sort_index()  # 时间序列排序
    # df1 = df.pivot_table(index=df.index,columns='ts_code',values='close')    # , dropna=False
    df1 = df.copy()  # 复制原始价格数据，避免修改传入的 df

    # ==== 2. 从 ts_code 自动提取行权价 ====
    def extract_strike(ts_code):  # 定义从期权代码中提取行权价的内部函数
        # 匹配 ts_code 中的数字部分作为行权价，例如 su2306-c-3500 → 3500
        m = re.search(r'(\d+)', ts_code.split('-')[-1])  # 从期权代码最后一段中匹配数字
        return int(m.group(1)) if m else np.nan  # 若匹配成功则返回行权价整数，否则返回 NaN
    mX = df1.columns.map(extract_strike).to_numpy()  # 提取每个列名里的行权价
    # mX = np.array(mx)  # 期权的行权价格跨度
    tdate = df1.index  # 资产的索引
    mP = df1.to_numpy()  # 转为numpy方便计算
    # ==== 3. 信号生成 ====
    signal = []  # 初始化信号列表，用于存放每次套利组合产生的交易信号
    # signal = pd.DataFrame(columns=['date','ts_code','signal','signal_w'])
    for mt in range(len(tdate)):  # 遍历每一个交易日期
        for targ in range(1, len(mX)):  # 遍历目标行权价位置
            for i in range(targ):  # 遍历目标行权价左侧的低行权价期权
                for j in range(targ + 1, len(mX)):  # 遍历目标行权价右侧的高行权价期权
                    if mP[mt][i] == 0 or mP[mt][j] == 0:  # 若参与插值的两端期权价格为 0，则跳过该组合
                        continue  # 跳过当前组合，继续下一组 i、j
                    # 解线性方程组，得到插值权重
                    A = np.array([[1, 1], [mX[i], mX[j]]])  # 对应位置的行权价格
                    b = np.array([1, mX[targ]])  # 行权价格
                    solution = np.linalg.solve(A, b)  # 做目标行权价格权重的解
                    # 插值价格
                    p = np.array([mP[mt][i], mP[mt][j]])  # 对应位置的期权价格
                    profolio = np.dot(p, solution)  # 组合的价格
                    # 价差条件
                    if mP[mt][targ] - profolio > n:  # 达到参数的价差，进行交易
                        date = tdate[mt]  # 时间
                        # 获取进行交易的股票代码
                        code1 = [s for s in df1.columns if str(mX[i]) in s][0]  # 做多的code
                        code2 = [s for s in df1.columns if str(mX[j]) in s][0]  # 做多的code
                        code3 = [s for s in df1.columns if str(mX[targ]) in s][0]  # 做空的code
                        code = [code1, code2, code3]  # 组成当前套利组合涉及的期权代码列表
                        for x,coden in enumerate(code):  # 遍历当前组合中的每个期权代码及其位置
                            # close = df.loc[(df.index == date) & (df['ts_code'] == coden), 'close']
                            close = df1.loc[date, coden]  # 获取当前日期下对应期权的收盘价格
                            # if close.notnull().any() and x != len(code) - 1:  # 判断价格是否存在，期权的发行日期不同
                            if pd.notna(close) and x != len(code) - 1:  # 判断价格是否存在，期权的发行日期不同
                                row_data = {'date': date,'ts_code':coden,'signal':1,'signal_w':solution[x]}  # 生成做多端期权的交易信号记录
                                # signal = signal.append(row_data, ignore_index=True)
                                signal.append(row_data)  # 将做多信号追加到信号列表
                                # df.loc[(df.index == date) & (df['ts_code'] == coden), 'signal'] += 1  # 做多
                                # df.loc[(df.index == date) & (df['ts_code'] == coden), 'signal_w'] = solution[x]  # 权重
                            # if close.notnull().any() and x == len(code) - 1:  # 判断价格是否存在，期权的发行日期不同
                            if pd.notna(close) and x == len(code) - 1:  # 判断价格是否存在，期权的发行日期不同
                                row_data = {'date': date, 'ts_code': coden, 'signal': -1, 'signal_w': 1}  # 生成做空端期权的交易信号记录
                                # signal = signal.append(row_data, ignore_index=True)
                                signal.append(row_data)  # 将做空信号追加到信号列表
                                # df.loc[(df.index == date) & (df['ts_code'] == coden), 'signal'] += -1  # 做空
                                # df.loc[(df.index == date) & (df['ts_code'] == coden), 'signal_w'] = 1  # 权重
    # signal = signal.set_index('date')  # 设置date为时间训练
    signal = pd.DataFrame(signal).set_index('date')  # 将信号列表转换为 DataFrame，并将 date 设置为索引

    # 按照 date 和 ts-code 列进行分组，并对 signal 和 signal_w 列求和
    signal = signal.groupby(['date', 'ts_code']).agg({'signal': 'sum', 'signal_w': 'sum'}).reset_index()  # 合并同一日期同一期权代码的重复信号
    # 对 signal_w 列取绝对值，计算每天内部的权重
    signal['signal_w_abs'] = signal['signal_w'].abs()  # 计算信号权重的绝对值
    signal['signal_w_abs'] = signal['signal'].abs() * signal['signal_w_abs']  # 用信号绝对值修正权重绝对值
    # 按照 date 列进行分组，并对 signal_w_abs 列进行归一化处理
    signal['signal_w'] = signal.groupby('date')['signal_w_abs'].transform(lambda x: x / x.sum())  # 计算同一天内各期权信号的归一化权重
    signal = signal.set_index('date')  # 设置时间为索引
    signal = signal[['ts_code', 'signal', 'signal_w']]  # pipline中的交易信号
    signal['signal'] = np.select([signal['signal'] > 1, signal['signal'] < 1], [1, -1], default=signal['signal'])  # 将聚合后的信号标准化为 1、-1 或原始值

    return signal


def Arbitrage_signal(df, n=2, backtest_trading_mode='backtest', **kwargs):     # ！！！范例，使用时需删除！！！
    """
        出处：《配对交易类-2_xxx》
        出处：《期权-对冲类-期权与期权组合的对冲-An-xxxxxxxxxxxxxxxx》
        功能：通过多空组合的期权资产组合的差值比较，释放交易信号
    :param df, Series: 计算的原始数据，索引需要是日期；
    :param n: int: 发出交易信号的阈值
    :param backtest_trading_mode, str: 回测、实盘交易模式
    :return: signal, DataFrame: 基于套利策略计算得到的交易信号；
             signal_weight, DataFrame: 基于套利策略计算得到的交易信号对应权重；
             res_optimize_metric, list: 基于寻优框架得到的寻优结果
    """
    # 获取套利框架所需全量原始因子数据，该变量数据不能修改，需要完整传入套利框架中
    dataFactorSrc = df.copy()
    # 转透视表：行索引为时间，列索引为标的；如果行、列有重复值，会聚合，默认aggfunc='mean';
    df_dataTrade = pd.pivot_table(df, index=df.index, columns='ts_code', values='close').sort_index()   # , dropna=False
    df_dataTrade = df_dataTrade.reindex(columns=df['ts_code'].dropna().drop_duplicates().tolist())      # 补齐行索引；

    # option_c_all 和 option_p_all 中：一个品种数量必须是 3；另一个品种数量必须是 0；其它所有品种数量必须都是 0；
    security_type_dict = get_security_type(df['ts_code'].dropna().drop_duplicates().tolist())
    if not (sorted([len(security_type_dict.get(k, []) or []) for k in ["option_c_all", "option_p_all"]]) == [0, 3] and all(len(security_type_dict.get(k, []) or []) == 0 for k in security_type_list if k not in ["option_c_all", "option_p_all"])):
        print("error：不满足：option_c_all 和 option_p_all 中：一个品种数量必须是 3；另一个品种数量必须是 0；其它所有品种数量必须都是 0；")
        return pd.DataFrame()

    # 调用因子函数，生成交易信号
    res_tmp = Arbitrage(df_dataTrade.copy(), n)
    res_factor = res_tmp.pivot_table(index=res_tmp.index, columns='ts_code', values='signal', aggfunc='mean', dropna=False)    # 如果有重复值用这一行 # 因子值转透视表
    res_factor = res_factor.reindex(columns=df['ts_code'].dropna().drop_duplicates().tolist())      # 补齐行索引；
    res_factor = res_factor.reindex(df_dataTrade.index)     # 补齐行索引；
    res_factor = res_factor.sort_index().shift(1)   # 将因子结果向后一个时间移动，防止出现未来数据。
    # 基于因子值生成信号的可执行的字符串表达式；此处不存在字符串表达式，所以给一个指定的占位符；
    signal_exp = """res_factor"""
    if (not backtest_trading_mode or ('backtest' in backtest_trading_mode if isinstance(backtest_trading_mode, str) else any(isinstance(x, str) and 'backtest' in x for x in backtest_trading_mode) if isinstance(backtest_trading_mode, (list, tuple, set)) else False)):
        signal, res_optimize_metric = cal_signal_metric(res_factor=res_factor, dataFactorSrc=dataFactorSrc, signal_exp=signal_exp, **kwargs)   # 绩效绩效评价
    else:
        signal, res_optimize_metric = eval(signal_exp.strip()), []      # 非回测模式，不执行绩效评级计算，直接计算信号值

    signal_weight = res_tmp.pivot_table(index=res_tmp.index, columns='ts_code', values='signal_w', aggfunc='mean', dropna=False)    # 如果有重复值用这一行    # 获取信号权重
    signal_weight = signal_weight.reindex(columns=df['ts_code'].dropna().drop_duplicates().tolist())    # 补齐行索引；
    signal_weight = signal_weight.reindex(df_dataTrade.index)   # 补齐行索引；
    signal_weight = signal_weight.sort_index().shift(1)

    # signal = signal.sort_index().shift(1)   # 将信号结果向后一个时间移动，防止出现未来数据。
    # signal_weight = signal_weight.sort_index().shift(1)   # 将信号权重结果向后一个时间移动，防止出现未来数据。

    return signal, signal_weight, res_optimize_metric


class ______期权_边界套利_特有_____():
    pass


def Boundary_Arbitrage(df, info_df, r=0, agg_rolling='sum'):
    """
        出处：《2020-10-15_天风证券_金融工程_金工深度_期权投资策略系列之一：300ETF期权套利，从理论到实践》P7-11
        功能：根据欧式期权无套利上下界计算边界偏离因子。
    :param df, DataFrame: 标的和期权的价格宽表，索引需要是日期；
    :param info_df, DataFrame: 字段：ts_code、maturity_date、option_C_P、strike_price"
    :param r, float or Series: default=0.0,无风险利率
    :param agg_rolling, str or callable: default='sum': 重复日期下连续边界因子的聚合方式；
    :return: factor, DataFrame：保留原始证券价格列，并增加上、下界偏离因子列。
    """
    security_type_dict = get_security_type(df.columns.tolist())  # 识别标的、股指和期货类型。
    stock_index_future = security_type_dict["stock"] + security_type_dict["future_all"]  # 合并股票和期货代码。

    underlying = stock_index_future[0]  # 提取标的。
    S = df[underlying]  # 提取标的价格。
    option_price = df.drop(columns=[underlying])  # 保留期权价格。

    info = info_df.copy()  # 复制基础信息，避免修改调用方数据。
    info["maturity_date"] = pd.to_datetime(info["maturity_date"])  # 将到期日转换为时间戳，便于计算剩余期限。
    call_put_map = info.set_index("ts_code")["option_C_P"].to_dict()  # 建立期权代码到认购/认沽类型的映射。
    K_map = info.set_index("ts_code")["strike_price"].to_dict()  # 建立期权代码到执行价的映射。
    maturity_map = info.set_index("ts_code")["maturity_date"].to_dict()  # 建立期权代码到到期日的映射。

    factor = df.copy()  # 初始化因子记录；因子定义函数只输出 factor，不直接输出交易信号。
    factor["upper_factor"] = np.nan  # 初始化期权价格高于上界时为正的偏离因子。
    factor["lower_factor"] = np.nan  # 初始化期权价格低于下界时为正的偏离因子。
    # 逐时间点计算各期权的无套利边界因子。
    for date in option_price.index:
        current_date = pd.Timestamp(date)# 统一当前时间的数据类型，便于与到期日相减。
        S_t = S.loc[date]
        if pd.isna(S_t) or S_t == 0:# 标的价格无效时无法计算期权边界，跳过该时间点。
            continue
        r_t = r.loc[date] if isinstance(r, pd.Series) else r  # 支持常数利率或按时间变化的利率序列。
        # 逐期权比较市场价格与无套利上下界。
        for code in option_price.columns:
            price = option_price.loc[date, code]  # 获取当前期权价格。
            if pd.isna(price) or price == 0:  # 期权价格无效时跳过。
                continue
            cp, K, maturity = call_put_map.get(code), K_map.get(code), maturity_map.get(code)  # 读取期权基础信息。
            if cp is None or pd.isna(K) or pd.isna(maturity):  # 基础信息不完整时跳过。
                continue
            # T = max((maturity - current_date).days / 252.0, 0)  # 计算剩余到期时间。
            T = max((maturity - current_date).days / 365.0, 0)  # 计算剩余到期时间。#分子得到的是自然日天数，分母也应该用自然日天数。
            disc = np.exp(-r_t * T)  # 计算执行价现金流的贴现系数。
            if cp == "C":
                upper, lower = S_t, max(S_t - K * disc, 0)  # 认购上界为标的价格，下界为贴现后的内在价值。
            elif cp == "P":
                upper, lower = K, max(K * disc - S_t, 0)  # 认沽上界为执行价，下界为贴现执行价减标的价格。
            else:   # 非法的期权类型不生成因子记录。
                continue
            factor.at[date, "upper_factor"] = price - upper  # 记录期权价格高于上界时为正的偏离值。
            factor.at[date, "lower_factor"] = lower - price  # 记录期权价格低于下界时为正的偏离值。
    factor = factor.groupby(level=0).agg(agg_rolling)   # agg_rolling 是可变常量，需要进参数
    return factor


def Boundary_Arbitrage_signal(df, r=0, agg_rolling='sum', backtest_trading_mode='backtest', **kwargs):
    """
        出处：《2020-10-15_天风证券_金融工程_金工深度_期权投资策略系列之一：300ETF期权套利，从理论到实践》P7-11
        功能：根据欧式期权无套利上下界产生交易信号。
    :param df, DataFrame: 计算的原始数据，索引需要是日期；一分钟价格矩阵
    :param r, float or Series: default=0.0无风险利率
    :param agg_rolling, str or callable: default='sum': 重复日期下连续因子的聚合方式；
    :return: signal, DataFrame: 基于套利策略计算得到的交易数据和信号；
             signal_weight, DataFrame: 基于套利策略计算得到的交易信号对应权重；
             res_optimize_metric, list: 基于寻优框架得到的寻优结果
    """
    dataFactorSrc = df.copy()
    df_tmp = df.assign(_row_id=range(len(df)))  # 增加唯一行号，避免重复索引导致误删。
    drop_row_id = df_tmp.groupby("ts_code", group_keys=False, sort=False).apply(lambda x: x.sort_index().ffill()).loc[lambda x: x[["buy1", "sale1", "maturity_date"]].isna().all(axis=1), "_row_id"]
    df = df_tmp.loc[~df_tmp["_row_id"].isin(drop_row_id)].drop(columns="_row_id")  # 只在原始 df_tmp 上删除对应行，不保留任何 ffill 结果
    df["ts_code1"] = df["ts_code"].astype(str).str.split(".").str[0].str.upper()
    df.loc[:, ["maturity_date"]] = df.groupby("ts_code1", sort=False)[["maturity_date"]].transform(lambda x: x.ffill().bfill()).values  # tushare标的名称与天软不一样，所以不能这样
    df = df.dropna(subset=['buy1', 'sale1', 'vol'], how='all')  # 删掉 tushare 引入的 "maturity_date", "list_date" 所在行

    # 构造分时价格矩阵
    df_dataTrade = df.pivot_table(index=df.index, columns="ts_code", values="close").sort_index()
    df_dataTrade = df_dataTrade.reindex(columns=df['ts_code'].dropna().drop_duplicates().tolist())
    info_df = df[df[["maturity_date", "option_C_P", "strike_price"]].notna().all(axis=1)][["ts_code", "maturity_date", "option_C_P", "strike_price"]].drop_duplicates("ts_code").reset_index(drop=True)

    # option_c_all 和 option_p_all 中：一个品种数量必须是 1；另一个品种数量必须是 0；stock 和 future_all 中的标的总数必须为1；其它所有品种数量必须都是 0；
    security_type_dict = get_security_type(df['ts_code'].dropna().drop_duplicates().tolist())
    if not (sorted([len(security_type_dict.get(k, []) or []) for k in ["option_c_all", "option_p_all"]]) == [0,1] and sum(len(security_type_dict.get(k, []) or [])for k in ["stock", "future_all"]) == 1 and all(len(security_type_dict.get(k, []) or []) == 0 for k in security_type_list if k not in ["option_c_all", "option_p_all", "stock", "future_all"])):
        print("error：不满足：option_c_all 和 option_p_all 中：一个品种数量必须是 1；另一个品种数量必须是 0；stock 和 future_all 中的标的总数必须为1；其它所有品种数量必须都是 0；")
        return pd.DataFrame()

    res_factor = Boundary_Arbitrage(df=df_dataTrade, info_df=info_df, r=r, agg_rolling=agg_rolling)  # 计算保留证券代码列的边界因子。
    res_factor = res_factor.sort_index().shift(1)  # 将因子滞后一根，避免未来数据。
    # 在信号函数判断期权类型，并生成标的、期权两腿信号。
    if security_type_dict["option_c_all"]:
        signal_exp = """pd.DataFrame(
            np.select([(res_factor["upper_factor"] > sig_coef_A).to_numpy()[:, None], (res_factor["lower_factor"] > sig_coef_B).to_numpy()[:, None]],
            [[1, -1], [-1, 1]],default=[np.nan, np.nan],),
            index=res_factor.index,
            columns=[c for c in res_factor.columns if c in df_dataTrade.columns],)
        """
    elif security_type_dict["option_p_all"]:
        signal_exp = """pd.DataFrame(
            np.select([(res_factor["upper_factor"] > sig_coef_A).to_numpy()[:, None], (res_factor["lower_factor"] > sig_coef_B).to_numpy()[:, None]],
            [[0, -1], [1, 1]],default=[np.nan, np.nan],),
            index=res_factor.index,
            columns=[c for c in res_factor.columns if c in df_dataTrade.columns],)
            """
    else:
        print(f"error：信号生成失败：未识别到有效的认购或认沽期权类型。")
        return pd.DataFrame(), pd.DataFrame(), []

    if (not backtest_trading_mode or ('backtest' in backtest_trading_mode if isinstance(backtest_trading_mode, str) else any(isinstance(x, str) and 'backtest' in x for x in backtest_trading_mode) if isinstance(backtest_trading_mode, (list, tuple, set)) else False)):
        signal, res_optimize_metric = cal_signal_metric(res_factor=res_factor, dataFactorSrc=dataFactorSrc, signal_exp=signal_exp, **kwargs)  # 将普通因子表和原始表达式交给回测框架处理。
    else:
        signal, res_optimize_metric = eval(signal_exp.strip()), []  # 非回测模式不执行绩效评价，直接计算信号值。
    signal_weight = get_signal_weight(signal)

    # signal = signal.sort_index().shift(1)   # 将信号结果向后一个时间移动，防止出现未来数据。
    # signal_weight = signal_weight.sort_index().shift(1)   # 将信号权重结果向后一个时间移动，防止出现未来数据。

    return signal, signal_weight, res_optimize_metric


