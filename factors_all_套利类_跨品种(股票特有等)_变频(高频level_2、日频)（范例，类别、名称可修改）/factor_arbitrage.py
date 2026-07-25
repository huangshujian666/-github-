# -*- coding: utf-8 -*-

import os
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

def get_adf_pvalue(series, min_observations=60):
    """
    对单个价格序列或收益率序列执行 ADF 平稳性检验，并返回 p 值。

    参数：
        series: Series
            待检验的价格序列、对数价格序列或对数收益率序列。
        min_observations: int
            执行 ADF 检验所需的最小有效样本数。

    返回：
        float
            ADF 检验 p 值；有效样本不足或检验无法执行时返回 np.nan。
    """
    # 将无穷值视为异常行情并删除缺失值，避免无效数据影响平稳性检验。
    clean_series = (
        pd.Series(series)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    # 有效样本不足时不进行统计检验，避免输出不可靠的平稳性结论。
    if len(clean_series) < min_observations:
        return np.nan

    try:
        # 使用 AIC 自动选择滞后阶数，返回 ADF 检验的 p 值。
        return float(adfuller(clean_series, autolag="AIC")[1])
    except (ValueError, np.linalg.LinAlgError):
        # 序列无法完成检验时返回空值，由上层逻辑判定为不通过。
        return np.nan


def get_i1_diagnostics(
    price_series=None,
    alpha=0.05,
    min_observations=60,
):
    """
    检查价格序列是否符合一阶单整 I(1) 特征。

    参数：
        price_series: Series
            单个标的的原始价格序列。
        alpha: float
            ADF 检验显著性水平；p 值小于该值时认为序列平稳。
        min_observations: int
            进行 ADF 检验所需的最小有效样本数。

    返回：
        dict
            包含价格对数序列的 ADF p 值、对数收益率的 ADF p 值，
            以及是否符合 I(1) 特征的判断结果。
    """
    # 未传入价格数据时无法执行单整性检验。
    if price_series is None:
        raise ValueError("price_series 不能为空。")

    # 非正价格无法计算对数，因此视为无效行情并排除出检验样本。
    clean_price_series = pd.Series(price_series).where(
        pd.Series(price_series) > 0
    )

    # 对数价格用于检验价格序列是否非平稳。
    log_price = np.log(clean_price_series)

    # 对数收益率用于检验一阶差分后是否平稳。
    log_return = log_price.diff()

    # 价格序列的 ADF p 值用于判断原序列是否非平稳。
    price_adf_pvalue = get_adf_pvalue(
        log_price,
        min_observations=min_observations,
    )

    # 收益率序列的 ADF p 值用于判断一阶差分后是否平稳。
    return_adf_pvalue = get_adf_pvalue(
        log_return,
        min_observations=min_observations,
    )

    # 原对数价格非平稳且一阶差分平稳时，判定该序列为 I(1)。
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
    price_table=None,
    candidate_codes=None,
    correlation_start=None,
    correlation_end=None,
    min_observations=60,
    min_correlation=0.70,
    adf_alpha=0.05,
    cointegration_alpha=0.05,
):
    """
    在候选标的中筛选满足 I(1)、E-G 协整和收益率相关性条件的品种对。

    参数：
        price_table: DataFrame
            行索引为日期、列为 ts_code、值为收盘价的价格透视表。
        candidate_codes: list
            参与配对筛选的候选合约代码列表。
        correlation_start: str 或 Timestamp
            相关性、单整性和协整性筛选的开始日期。
        correlation_end: str 或 Timestamp
            相关性、单整性和协整性筛选的结束日期。
        min_observations: int
            每个候选品种对所需的最小有效样本数。
        min_correlation: float
            对数收益率相关系数的最低准入阈值。
        adf_alpha: float
            单整性检验使用的 ADF 显著性水平。
        cointegration_alpha: float
            E-G 协整检验和残差 ADF 检验使用的显著性水平。

    返回：
        tuple 或 None
            筛选成功时返回
            (x_code, y_code, correlation, observation_count)；
            没有合格品种对时返回 None。
    """
    # 未传入价格表时，无法进行候选品种筛选。
    if price_table is None:
        raise ValueError("price_table 不能为空。")

    # 候选列表至少需要两个标的，才能构成套利品种对。
    if candidate_codes is None or len(candidate_codes) < 2:
        raise ValueError("candidate_codes 至少需要填写两个候选标的。")

    # 保留候选标的原有顺序并去除重复代码，避免重复计算同一品种对。
    candidate_codes = list(dict.fromkeys(candidate_codes))

    # 使用价格表副本，避免修改框架传入的原始数据。
    price_table = price_table.copy()

    # 将价格表索引统一转换为时间格式，保证日期筛选可比较。
    price_table.index = pd.to_datetime(price_table.index)

    # 检查配置的候选标的是否均已出现在价格表中。
    missing_codes = [
        code
        for code in candidate_codes
        if code not in price_table.columns
    ]
    if missing_codes:
        raise ValueError(
            f"候选标的未出现在价格数据中：{missing_codes}。"
            f"实际列为：{price_table.columns.tolist()}"
        )

    # 筛选期必须完整填写，否则无法确定统计检验样本。
    if correlation_start is None or correlation_end is None:
        raise ValueError("必须填写 correlation_start 和 correlation_end。")

    # 将配置日期转换为 Timestamp，用于价格表时间索引筛选。
    correlation_start = pd.Timestamp(correlation_start)
    correlation_end = pd.Timestamp(correlation_end)

    # 开始日期不能晚于结束日期。
    if correlation_start > correlation_end:
        raise ValueError("correlation_start 不能晚于 correlation_end。")

    # 截取候选品种在统计筛选期内的价格数据。
    sample_prices = price_table.loc[
        (price_table.index >= correlation_start)
        & (price_table.index <= correlation_end),
        candidate_codes,
    ]

    # 筛选期没有价格数据时，不允许静默选择候选品种对。
    if sample_prices.empty:
        raise ValueError(
            "相关性筛选期内没有价格数据。请检查数据库是否包含 "
            f"{correlation_start.date()} 至 {correlation_end.date()} 的历史数据。"
        )

    # 保存同时通过全部统计条件的候选品种对。
    valid_pairs = []

    # 对候选标的进行两两组合，逐对执行统计筛选。
    for x_code, y_code in combinations(candidate_codes, 2):
        # 仅保留两腿共同有价格的交易日，保证两腿使用严格日期交集。
        pair_prices = sample_prices[[x_code, y_code]].dropna()

        # 非正价格无法计算对数价格和对数收益率，因此从统计样本中排除。
        pair_prices = pair_prices[
            (pair_prices[x_code] > 0)
            & (pair_prices[y_code] > 0)
        ]

        # 有效价格样本不足时，不进行后续统计检验。
        if len(pair_prices) < min_observations:
            continue

        # 分别判断 X、Y 两腿的对数价格序列是否符合 I(1)。
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

        # 任一腿不满足 I(1) 时，该品种对不进入协整和相关性筛选。
        if not (x_i1["is_i1"] and y_i1["is_i1"]):
            print(
                f"I(1)未通过：{x_code}/{y_code}；"
                f"X价格ADF={x_i1['price_adf_pvalue']:.4f}，"
                f"X收益率ADF={x_i1['return_adf_pvalue']:.4f}；"
                f"Y价格ADF={y_i1['price_adf_pvalue']:.4f}，"
                f"Y收益率ADF={y_i1['return_adf_pvalue']:.4f}"
            )
            continue

        # 使用 E-G p 值和残差 ADF p 值共同判断该品种对是否协整。
        cointegration = get_cointegration_diagnostics(
            pair_prices[x_code],
            pair_prices[y_code],
            alpha=cointegration_alpha,
            min_observations=min_observations,
        )

        # 协整关系不成立时，不允许该品种对参与交易。
        if not cointegration["is_cointegrated"]:
            print(
                f"协整未通过：{x_code}/{y_code}；"
                f"E-G p值={cointegration['eg_pvalue']:.4f}，"
                f"残差ADF p值={cointegration['resid_adf_pvalue']:.4f}"
            )
            continue

        # 使用共同交易日的对数收益率计算两腿价格联动性。
        pair_returns = np.log(pair_prices).diff().dropna()

        # 对数收益率样本不足时，相关系数不具备筛选意义。
        if len(pair_returns) < min_observations:
            continue

        # 计算该品种对的对数收益率 Pearson 相关系数。
        correlation = pair_returns[x_code].corr(pair_returns[y_code])

        # 仅保留达到配置相关性阈值的品种对。
        if pd.notna(correlation) and correlation >= min_correlation:
            valid_pairs.append(
                (x_code, y_code, float(correlation), len(pair_returns))
            )

    # 没有品种对通过全部条件时，本轮应输出空仓信号。
    if not valid_pairs:
        print("没有候选对同时通过 I(1)、E-G 协整和相关性筛选，本轮不交易。")
        return None

    # 在合格候选中选择对数收益率相关性最高的一对。
    return max(valid_pairs, key=lambda item: item[2])

def get_cointegration_diagnostics(
    x_price=None,
    y_price=None,
    alpha=0.05,
    min_observations=60,
):
    """
    对两个价格序列执行 E-G 两步协整检验，并返回协整诊断结果。

    参数：
        x_price: Series
            回归方程中的自变量 X 的原始价格序列。
        y_price: Series
            回归方程中的因变量 Y 的原始价格序列。
        alpha: float
            E-G 协整检验和残差 ADF 检验的显著性水平。
        min_observations: int
            执行协整检验所需的最小有效样本数。

    返回：
        dict
            包含 E-G p 值、残差 ADF p 值、截距、beta 和协整通过标志。
    """
    # 两腿价格数据缺失时，无法构建协整检验样本。
    if x_price is None or y_price is None:
        raise ValueError("x_price 和 y_price 均不能为空。")

    # 将两腿价格按日期合并，确保后续检验使用相同交易日。
    pair_prices = pd.concat(
        [
            pd.Series(x_price, name="x_price"),
            pd.Series(y_price, name="y_price"),
        ],
        axis=1,
    )

    # 无穷值、缺失值和非正价格不能参与对数价格协整检验。
    pair_prices = pair_prices.replace([np.inf, -np.inf], np.nan).dropna()
    pair_prices = pair_prices[
        (pair_prices["x_price"] > 0)
        & (pair_prices["y_price"] > 0)
    ]

    # 样本不足时不输出协整结论，并明确标记为不通过。
    if len(pair_prices) < min_observations:
        return {
            "eg_pvalue": np.nan,
            "resid_adf_pvalue": np.nan,
            "alpha": np.nan,
            "beta": np.nan,
            "is_cointegrated": False,
        }

    # 对数价格用于构建长期均衡关系和残差序列。
    log_x_price = np.log(pair_prices["x_price"])
    log_y_price = np.log(pair_prices["y_price"])

    try:
        # E-G 两步法检验两个对数价格序列是否存在协整关系。
        _, eg_pvalue, _ = coint(log_y_price, log_x_price, trend="c")

        # 构建带截距项的 OLS 回归自变量矩阵。
        x_matrix = np.column_stack(
            [np.ones(len(log_x_price)), log_x_price.to_numpy()]
        )

        # 估计长期均衡方程的截距和 beta。
        alpha_value, beta = np.linalg.lstsq(
            x_matrix,
            log_y_price.to_numpy(),
            rcond=None,
        )[0]

        # 根据滚动回归方程计算残差，用于残差平稳性检验。
        residual = log_y_price - alpha_value - beta * log_x_price

        # 残差平稳意味着价差具有均值回复特征。
        resid_adf_pvalue = get_adf_pvalue(
            residual,
            min_observations=min_observations,
        )

    except (ValueError, np.linalg.LinAlgError):
        # 回归或检验失败时，不允许将该品种对判定为协整。
        eg_pvalue = np.nan
        resid_adf_pvalue = np.nan
        alpha_value = np.nan
        beta = np.nan

    # E-G 与残差 ADF 均通过显著性检验时，判定协整关系成立。
    is_cointegrated = (
        pd.notna(eg_pvalue)
        and pd.notna(resid_adf_pvalue)
        and eg_pvalue < alpha
        and resid_adf_pvalue < alpha
    )

    return {
        "eg_pvalue": eg_pvalue,
        "resid_adf_pvalue": resid_adf_pvalue,
        "alpha": alpha_value,
        "beta": beta,
        "is_cointegrated": is_cointegrated,
    }

def resid(
    df=None,
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
            行索引为日期、列为两个标的 ts_code、值为收盘价的价格透视表。
        window: int
            滚动回归、协整检验和残差统计使用的窗口长度。
        adf_alpha: float
            残差 ADF 检验的显著性水平。
        cointegration_alpha: float
            E-G 协整检验的显著性水平。
        require_rolling_cointegration: bool
            是否要求每个滚动窗口均通过协整检验。

    返回：
        DataFrame
            包含价格、alpha、beta、残差、残差均值、残差标准差、
            E-G p 值、残差 ADF p 值和协整通过标志。
    """
    # 未传入价格数据时，无法计算残差套利因子。
    if df is None:
        raise ValueError("df 不能为空。")

    # 创建数据副本并按日期排序，避免修改框架传入的原始数据。
    price_table = df.astype(float).sort_index().copy()

    # 该因子只允许对恰好两个标的构建价差。
    if price_table.shape[1] != 2:
        raise ValueError("resid 因子要求输入恰好两个标的。")

    # 按列顺序确定回归中的 X 和 Y。
    x_code = price_table.columns[0]
    y_code = price_table.columns[1]

    # 创建因子结果表，并预先定义全部诊断字段。
    res_factor = price_table.copy()
    res_factor["alpha"] = np.nan
    res_factor["beta"] = np.nan
    res_factor["resid"] = np.nan
    res_factor["resid_mean"] = np.nan
    res_factor["resid_std"] = np.nan
    res_factor["eg_pvalue"] = np.nan
    res_factor["resid_adf_pvalue"] = np.nan
    res_factor["cointegration_pass"] = False

    # 每个时点仅使用当前及之前 window 个交易日数据，避免未来数据。
    for end_idx in range(window - 1, len(price_table)):
        # 截取当前滚动窗口内的两腿原始价格。
        sample_prices = price_table[[x_code, y_code]].iloc[
            end_idx - window + 1:end_idx + 1
        ]

        # 缺失、无穷和非正价格无法计算对数价格，因此不参与统计样本。
        sample_prices = sample_prices.replace(
            [np.inf, -np.inf],
            np.nan,
        ).dropna()
        sample_prices = sample_prices[
            (sample_prices[x_code] > 0)
            & (sample_prices[y_code] > 0)
        ]

        # 有效样本不足完整窗口时，不生成不可靠的因子值。
        if len(sample_prices) < window:
            continue

        # 对数价格用于滚动 OLS 长期均衡方程和残差计算。
        log_x_price = np.log(sample_prices[x_code])
        log_y_price = np.log(sample_prices[y_code])

        # 获取当前窗口的 E-G、残差 ADF、截距和 beta 诊断结果。
        diagnostics = get_cointegration_diagnostics(
            sample_prices[x_code],
            sample_prices[y_code],
            alpha=cointegration_alpha,
            min_observations=window,
        )

        # 读取当前窗口的滚动回归参数。
        alpha_value = diagnostics["alpha"]
        beta = diagnostics["beta"]

        # 回归参数不可用时，不生成残差和交易依据。
        if pd.isna(alpha_value) or pd.isna(beta):
            continue

        # 按研报公式计算当前窗口的残差序列。
        residual_series = (
            log_y_price
            - alpha_value
            - beta * log_x_price
        )

        # 根据配置决定是否强制要求当前窗口协整通过。
        cointegration_pass = (
            not require_rolling_cointegration
            or diagnostics["is_cointegrated"]
        )

        # 当前滚动窗口最后一个日期对应当前可输出的因子时点。
        current_date = price_table.index[end_idx]

        # 保存当前窗口估计得到的截距和 beta。
        res_factor.loc[current_date, "alpha"] = alpha_value
        res_factor.loc[current_date, "beta"] = beta

        # 保存当前时点残差及窗口内残差统计量。
        res_factor.loc[current_date, "resid"] = residual_series.iloc[-1]
        res_factor.loc[current_date, "resid_mean"] = residual_series.mean()
        res_factor.loc[current_date, "resid_std"] = residual_series.std(ddof=1)

        # 保存协整诊断结果，供后续审计和信号风控使用。
        res_factor.loc[current_date, "eg_pvalue"] = diagnostics["eg_pvalue"]
        res_factor.loc[
            current_date,
            "resid_adf_pvalue",
        ] = diagnostics["resid_adf_pvalue"]
        res_factor.loc[
            current_date,
            "cointegration_pass",
        ] = cointegration_pass

    return res_factor



def resid_signal(
    df=None,
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
    cooldown_period=0,
    contract_multipliers=None,
    margin_rates=None,
    minimum_lots=None,
    backtest_trading_mode="backtest",
    **kwargs,
):
    """
    根据滚动残差、协整状态和持仓状态生成跨品种套利信号。

    参数：
        df: DataFrame
            框架传入的原始长表，至少包含 ts_code 和 close。
        window: int
            滚动 OLS、协整检验和残差统计的窗口长度。
        X: float
            开仓阈值倍数；本研报复现中取 2。
        stop_loss_X: float
            止损阈值倍数；本研报复现中取 3。
        threshold_mode: str
            阈值模式；当前仅支持 absolute。
        candidate_codes: list
            参与相关性、单整性和协整性筛选的候选合约代码。
        correlation_start: str 或 Timestamp
            候选品种统计筛选开始日期。
        correlation_end: str 或 Timestamp
            候选品种统计筛选结束日期。
        correlation_min_observations: int
            候选品种对统计筛选的最小有效样本数。
        correlation_min_value: float
            候选品种对对数收益率相关系数最低阈值。
        adf_alpha: float
            ADF 单整性和残差平稳性检验显著性水平。
        cointegration_alpha: float
            E-G 协整检验显著性水平。
        require_rolling_cointegration: bool
            是否要求每个滚动窗口均通过协整检验。
        cooldown_period: int
            止损平仓后禁止重新开仓的交易日数量。
        contract_multipliers: dict
            各合约的合约乘数，用于计算两腿保证金占用比例。
        margin_rates: dict
            各合约的保证金率，用于计算两腿保证金占用比例。
        minimum_lots: dict
            各合约的最小手数；当前目标比例框架仅校验该配置，
            不在因子函数内直接进行整数手数取整。
        backtest_trading_mode: str
            框架传入的回测交易模式参数。
        kwargs: dict
            框架额外传入的配置参数。

    返回：
        tuple
            第一个元素为日期 × ts_code 的交易信号表；
            第二个元素为对应的信号权重表。
    """
    # 未传入原始行情数据时，无法生成因子和交易信号。
    if df is None:
        raise ValueError("df 不能为空。")

    # 原始数据必须包含证券代码和收盘价字段。
    required_columns = {"ts_code", "close"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"df 缺少必要字段：{sorted(missing_columns)}。")

    # 使用副本并统一日期索引格式，避免修改框架传入的原始数据。
    source_data = df.copy()
    source_data.index = pd.to_datetime(source_data.index)

    # 构建日期—合约组合，用于检查是否存在重复行情。
    date_code_table = pd.DataFrame(
        {
            "date": source_data.index,
            "ts_code": source_data["ts_code"].to_numpy(),
        },
        index=source_data.index,
    )

    # 同一日期和同一合约只能有一条行情，重复时必须报错。
    duplicate_mask = date_code_table.duplicated(
        subset=["date", "ts_code"],
        keep=False,
    )
    if duplicate_mask.any():
        duplicate_records = date_code_table.loc[duplicate_mask]
        raise ValueError(
            "发现重复的日期—合约行情记录："
            f"{duplicate_records.head().to_dict('records')}"
        )

    # 生成日期 × 合约的收盘价透视表；已验证唯一性，因此不进行均值聚合。
    source_data = source_data.assign(date=source_data.index)
    trade_price_table = source_data.pivot(
        index="date",
        columns="ts_code",
        values="close",
    ).sort_index()

    # 未单独配置候选标的时，使用行情表中的全部合约代码。
    if candidate_codes is None:
        candidate_codes = trade_price_table.columns.tolist()

    # 保留候选列表原顺序并去除重复代码。
    candidate_codes = list(dict.fromkeys(candidate_codes))

    # 根据 I(1)、E-G 协整和对数收益率相关性选择套利品种对。
    selection_result = select_pair_by_correlation(
        price_table=trade_price_table,
        candidate_codes=candidate_codes,
        correlation_start=correlation_start,
        correlation_end=correlation_end,
        min_observations=correlation_min_observations,
        min_correlation=correlation_min_value,
        adf_alpha=adf_alpha,
        cointegration_alpha=cointegration_alpha,
    )

    # 没有品种对通过统计筛选时，所有候选标的均输出空仓信号。
    if selection_result is None:
        print("本轮没有通过统计筛选的品种对，输出全 0 信号。")

        signal = pd.DataFrame(
            0.0,
            index=trade_price_table.index,
            columns=candidate_codes,
        )
        signal_weight = pd.DataFrame(
            0.0,
            index=trade_price_table.index,
            columns=candidate_codes,
        )

        return signal, signal_weight

    # 读取筛选出的 X、Y 品种及其相关性诊断结果。
    x_code, y_code, correlation, observation_count = selection_result

    print(
        f"相关性筛选结果：{x_code} 与 {y_code}；"
        f"对数收益率相关系数={correlation:.4f}；"
        f"有效样本数={observation_count}"
    )

    # 仅对筛选出的两腿构建滚动残差因子。
    selected_price_table = trade_price_table[[x_code, y_code]]

    # 计算滚动 OLS 残差、协整诊断和残差统计量。
    factor_result = resid(
        selected_price_table.copy(),
        window=window,
        adf_alpha=adf_alpha,
        cointegration_alpha=cointegration_alpha,
        require_rolling_cointegration=require_rolling_cointegration,
    )

    # 读取框架传入的配置，用于保存本次滚动回归诊断结果。
    param_config = kwargs.get("param_config") or {}

    # 获取本次回测对应的结果目录和配置编号。
    output_dir = param_config.get("output_dir", "result/")
    config_index = param_config.get("config_index", 0)
    factor_name = param_config.get("func_name_factor", "resid_signal")

    # 兼容框架可能传入列表形式的结果目录配置。
    if isinstance(output_dir, list):
        output_dir = output_dir[0]

    # 保存 alpha、beta、残差、p 值及协整标志，供后续核验。
    diagnostics_path = os.path.join(
        output_dir,
        f"config{config_index}",
        f"{factor_name}_diagnostics.csv",
    )
    os.makedirs(os.path.dirname(diagnostics_path), exist_ok=True)
    factor_result.to_csv(
        diagnostics_path,
        encoding="utf-8-sig",
    )

    # 当前研报复现仅使用标准差倍数阈值，不支持分位数模式。
    if threshold_mode != "absolute":
        raise ValueError(
            '当前研报复现只支持 threshold_mode="absolute"。'
        )

    # 因子计算结果整体后移一期，保证当期交易不使用未来数据。
    factor_result = factor_result.sort_index().shift(1)

    # 为全部候选标的初始化空仓信号；未入选标的始终保持 0。
    signal = pd.DataFrame(
        0.0,
        index=factor_result.index,
        columns=candidate_codes,
    )

    # position 为当前价差仓位：1 表示多 X 空 Y，-1 表示空 X 多 Y。
    position = 0

    # previous_z_score 用于判断残差是否刚刚上穿或下穿开仓阈值。
    previous_z_score = np.nan

    # cooldown_remaining 表示止损后剩余禁止开仓的交易日数。
    cooldown_remaining = 0

    # 状态机必须按时间顺序运行，因此逐交易日生成信号。
    for current_date, row in factor_result.iterrows():
        # 残差标准差无效时无法计算 z-score，当日保持空仓。
        residual_std = row["resid_std"]
        if pd.isna(residual_std) or residual_std <= 0:
            position = 0
            previous_z_score = np.nan
            continue

        # 计算当前残差相对滚动均值的标准化偏离程度。
        z_score = (
            row["resid"] - row["resid_mean"]
        ) / residual_std

        # 读取当前滚动窗口是否通过协整检验。
        cointegration_pass = row["cointegration_pass"]

        # 残差无效或协整失败时，强制平仓且不产生新交易。
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

        # 止损后的冷却期内保持空仓，避免阈值附近反复开平仓。
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            previous_z_score = np.nan
            continue

        # 空仓状态下，仅在残差刚刚穿越开仓阈值时开仓。
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

            # 残差上穿 2σ 时，做多 X、做空 Y。
            if upper_crossed:
                position = 1

            # 残差下穿 -2σ 时，做空 X、做多 Y。
            elif lower_crossed:
                position = -1

        # 持仓状态下，残差回归均值范围时执行平仓。
        elif abs(z_score) <= X:
            position = 0

        # 残差达到或超过 3σ 时执行止损平仓，并启动冷却期。
        elif abs(z_score) >= stop_loss_X:
            position = 0
            cooldown_remaining = cooldown_period

        # position 为 1 时，输出多 X、空 Y 的两腿信号。
        if position == 1:
            signal.loc[current_date, [x_code, y_code]] = [1.0, -1.0]

        # position 为 -1 时，输出空 X、多 Y 的两腿信号。
        elif position == -1:
            signal.loc[current_date, [x_code, y_code]] = [-1.0, 1.0]

        # 保存当前 z-score，供下一交易日判断是否发生阈值穿越。
        previous_z_score = z_score

        # 将配置参数转换为空字典默认值，便于检查每个合约是否具有完整配比参数。
    contract_multipliers = contract_multipliers or {}
    margin_rates = margin_rates or {}
    minimum_lots = minimum_lots or {}

    # 两腿均必须配置合约乘数、保证金率和最小手数。
    weighting_codes = [x_code, y_code]
    missing_weighting_config = {
        "contract_multipliers": [
            code
            for code in weighting_codes
            if code not in contract_multipliers
        ],
        "margin_rates": [
            code
            for code in weighting_codes
            if code not in margin_rates
        ],
        "minimum_lots": [
            code
            for code in weighting_codes
            if code not in minimum_lots
        ],
    }

    # 缺少任何配比参数时，不允许静默使用通用等权重。
    if any(missing_weighting_config.values()):
        raise ValueError(
            "筛选品种缺少 beta 配比参数："
            f"{missing_weighting_config}"
        )

    # 当前框架按目标比例下单，因此此处输出每条腿的目标保证金占用比例。
    signal_weight = pd.DataFrame(
        0.0,
        index=signal.index,
        columns=signal.columns,
    )

    # 按每个交易日的滚动 beta、价格、合约乘数和保证金率计算两腿权重。
    for current_date, factor_row in factor_result.iterrows():
        # 当日未持有筛选品种对时，两腿权重保持为 0。
        if (
                signal.loc[current_date, x_code] == 0
                and signal.loc[current_date, y_code] == 0
        ):
            continue

        # 读取已 T+1 延迟的 beta 和两腿价格。
        beta = factor_row["beta"]
        x_price = factor_row[x_code]
        y_price = factor_row[y_code]

        # beta 或价格无效时，不允许生成不可靠的目标权重。
        if (
                pd.isna(beta)
                or pd.isna(x_price)
                or pd.isna(y_price)
                or x_price <= 0
                or y_price <= 0
        ):
            continue

        # 读取两腿的合约乘数、保证金率和最小手数配置。
        x_multiplier = float(contract_multipliers[x_code])
        y_multiplier = float(contract_multipliers[y_code])
        x_margin_rate = float(margin_rates[x_code])
        y_margin_rate = float(margin_rates[y_code])
        x_minimum_lot = float(minimum_lots[x_code])
        y_minimum_lot = float(minimum_lots[y_code])

        # 合约参数必须为正值，否则不能计算保证金占用比例。
        if (
                x_multiplier <= 0
                or y_multiplier <= 0
                or x_margin_rate <= 0
                or y_margin_rate <= 0
                or x_minimum_lot <= 0
                or y_minimum_lot <= 0
        ):
            raise ValueError(
                "合约乘数、保证金率和最小手数必须均为正数。"
            )

        # 按滚动 beta 估计 X 腿相对 Y 腿的对冲名义规模。
        x_margin_exposure = (
                abs(beta)
                * x_price
                * x_multiplier
                * x_margin_rate
        )
        y_margin_exposure = (
                y_price
                * y_multiplier
                * y_margin_rate
        )

        # 两腿保证金占用总额为 0 时，不生成权重。
        total_margin_exposure = (
                x_margin_exposure + y_margin_exposure
        )
        if total_margin_exposure <= 0:
            continue

        # 将两腿保证金占用归一化为目标比例。
        signal_weight.loc[current_date, x_code] = (
                x_margin_exposure / total_margin_exposure
        )
        signal_weight.loc[current_date, y_code] = (
                y_margin_exposure / total_margin_exposure
        )

    return signal, signal_weight




