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


