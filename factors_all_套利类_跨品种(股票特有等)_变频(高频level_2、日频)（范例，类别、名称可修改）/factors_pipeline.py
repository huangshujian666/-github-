# -*- coding: utf-8 -*-

import copy
import pandas as pd
import os
import importlib
import pickle
import backtest
from run_func import multi_run
import dataGet_Func as dataGet


class G:
    """
    全局对象 G，用来存储用户的全局数据
    """
    pass


# 创建全局对象g
g = G()


def initialize(context):
    """ 吧
        用户初始设定，在回测时只会在启动的时候触发一次
    :param context: Context对象，因子的各种属性上下文
    """
    if not os.path.exists(context.config['factor_dir'] + context.config['file_name_factor_IO']):
        # 获取源数据并筛选列名；
        g.dataTrade, dataFactorSrc, g.dataBenchmark, context.fired = getattr(dataGet, "dataGet_filter")(context.config["param_dataSrc"])
        #  ——————————————————————————————以下为因子逻辑——————————————————————————————
        from dataGet_Func_api import get_ts_code_order, get_align_data
        ts_code_order = get_ts_code_order(dataFactorSrc, ts_col='ts_code', date_col='date')
        dataTrade, lst_src, dataFactorSrc = get_align_data(dataFactorSrc, symbol_list=ts_code_order)
        g.dataTrade = g.dataTrade.reindex(dataTrade.index)
        # 找出两边共有的列，并且顺序严格按照 dataTrade.columns
        common_cols = [c for c in dataTrade.columns if c in g.dataTrade.columns]
        # 用 dataTrade 替换 g.dataTrade 中的同名列
        g.dataTrade[common_cols] = dataTrade[common_cols]
        # 调整列顺序：重复列按 dataTrade 顺序排，非重复列保留在后面，保留原来的相对顺序
        g.dataTrade = g.dataTrade[common_cols + [c for c in g.dataTrade.columns if c not in common_cols]]
        from backtest_optimize import get_security_type, cal_signal_metric
        security_type_dict = get_security_type(g.dataTrade.columns)
        security_type_items = [(k, security_type_dict.get(k, [])) for k in ["fund", "stock", "future", "option_cp"] if security_type_dict.get(k, [])]   # 保留非空的键值对
        g.security_direction_subportfolio_index = {security: {"long": i * 2 + 1, "short": i * 2 + 2} for i, (security_type, security_list) in enumerate(security_type_items) for security in security_list}  # 按非空品种顺序，每个品种依次分配两个账号编号
        # 带有买一卖一价的交易价格数据；同时也是对齐不同标的的索引。
        g.df_dataTrade_buy1_sale1 = pd.concat([dataFactorSrc[dataFactorSrc['ts_code']==symbol][['close', 'buy1', 'sale1']].astype(str).apply(lambda row: '_'.join(row), axis=1) if {'close', 'buy1', 'sale1'}.issubset(dataFactorSrc.columns) else dataFactorSrc['close'].astype(str) for symbol in ts_code_order], axis=1)
        g.df_dataTrade_buy1_sale1.columns = ts_code_order

        #  ——————————————————————————————因子信号生成（可以修改）——————————————————————————————
        # # 判断是否存在当前模型文件，或者在当前模型函文件中是否存在对应功能函数
        # factor_module, is_func_name_factor = backtest.get_factor_module(context.config['func_name_factor'], context.config['file_name_model'], context.config['model_dir'], os.path.basename(os.getcwd()))
        if not importlib.util.find_spec(context.config['model_dir'] + context.config['file_name_model']) \
                or not hasattr(importlib.import_module(context.config['model_dir'] + context.config['file_name_model']), context.config['func_name_factor']):
            context.fired = True
            context.dataTrade, context.dataFactorSrc = g.dataTrade, dataFactorSrc
            print("该因子不在因子定义中！或该因子未指定功能模块文件！")
            return
        factor_module = importlib.import_module(context.config['model_dir'] + context.config['file_name_model'])
        if isinstance(context.config['param_factor'], dict):  # 如果参数是字典，则将股票数据和字典解包作为参数传递
            # g.signals, g.weight_tb = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, **context.config['param_factor'])
            # g.signals = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, **context.config['param_factor'])
            # g.signals, g.weight_tb, *extra = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, **{**(context.config.get('param_factor') or {}), 'param_config': copy.deepcopy(context.config)})
            res_factor = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, **{**(context.config.get('param_factor') or {}), 'param_config': copy.deepcopy(context.config)})
        elif isinstance(context.config['param_factor'], list):  # 如果参数是列表，则将股票数据和列表解包作为参数传递
            # g.signals, g.weight_tb = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, *context.config['param_factor'])
            # g.signals = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, *context.config['param_factor'])
            # g.signals, g.weight_tb, *extra = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, *context.config['param_factor'], param_config=copy.deepcopy(context.config))
            res_factor = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, *context.config['param_factor'], param_config=copy.deepcopy(context.config))
        else:  # 没有给出任何参数
            # g.signals, g.weight_tb = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc)
            # g.signals = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc)
            # g.signals, g.weight_tb, *extra = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, param_config=copy.deepcopy(context.config))
            res_factor = getattr(factor_module, context.config['func_name_factor'])(dataFactorSrc, param_config=copy.deepcopy(context.config))
        #  ——————————————————————————————因子信号生成（结束）——————————————————————————————
        g.signals, *extra = res_factor if isinstance(res_factor, tuple) else (res_factor,)
        g.weight_tb = extra[0] if extra and len(extra) > 0 else pd.DataFrame()
        if extra and len(extra) > 1:
            context.all_result['res_optimize'] = extra[1]
            g.signals = g.signals.head(1) if len(g.signals.index) > 0 else pd.DataFrame()
        elif g.signals.empty:
            g.signals = dataFactorSrc.head(1)
        # else:     # elif context.backtest_type == 'optimize':
        #     _, context.all_result['res_optimize'] = cal_signal_metric(res_factor=g.signals, dataFactorSrc=dataFactorSrc, signal_exp="""""", logger=None, **{'param_config': copy.deepcopy(context.config)})


        #  ——————————————————————————————以下为因子交易时间范围及初始化——————————————————————————————
        # # 调用 get_trade_cal 函数生成 date_range_src ,用于交易循环遍历所依据的日期序列，源数据文件存储在 context.data_dir 路径中
        # date_range_src = dataGet.get_trade_cal(data_dir=context.data_dir)
        # # 将 date_range_src 转为只含有开盘日期的series
        # date_range_src = pd.Series(date_range_src[(date_range_src['is_open'] == 1)]['cal_date'].values)
        # # 如果需要修改 date_range_src 的原始时间序列内容，需在该注释下修改，将修改后的时间序列再对context对应属性进行初始化；
        date_range_src = pd.to_datetime(pd.Series(g.signals.index).drop_duplicates().sort_values())  # 使用现有数据构造date_range样例；

        # 用 date_range_src 补齐 g.dataTrade的索引日期（索引日期必须是datetime.datetime时间戳格式）;
        g.dataTrade = pd.DataFrame(index=date_range_src).combine_first(g.dataTrade)
        # 用 date_range_src 补齐 g.signals的索引日期（索引日期必须是datetime.datetime时间戳格式）;combine_first要求g.signals为DataFrame；
        g.signals = pd.DataFrame(index=date_range_src).combine_first(pd.DataFrame(g.signals))
        g.weight_tb = pd.DataFrame(index=date_range_src).combine_first(pd.DataFrame(g.weight_tb))
        # 用 date_range_src 补齐g.dataBenchmark的索引日期（索引日期必须是datetime.datetime时间戳格式）;
        g.dataBenchmark = pd.DataFrame(index=date_range_src).combine_first(g.dataBenchmark) if not pd.DataFrame(g.dataBenchmark).empty else None

        # # # 为了便于调试因子，暂时先不生成离线因子文件
        # # 将回测需要的数据存入字典保存到 dataSrc_path
        # with open(context.config['factor_dir'] + context.config['file_name_factor_IO'], "wb") as f:
        #     pickle.dump({'dataTrade': g.dataTrade, 'signals': g.signals, 'dataBenchmark': g.dataBenchmark, 'date_range_src': date_range_src, 'config': context.config, 'dataFactorSrc': dataFactorSrc}, f)
        # #     pickle.dump({'dataTrade': g.dataTrade, 'signals': g.signals, 'weight_tb': g.weight_tb, 'dataBenchmark': g.dataBenchmark, 'date_range_src': date_range_src, 'config': context.config, 'dataFactorSrc': dataFactorSrc}, f)

    else:
        # 直接读取已经生成的因子文件并获取各变量数据
        with open(context.config['factor_dir'] + context.config['file_name_factor_IO'], 'rb') as f:
            dataSrc_dict = pickle.load(f)
        # 按键名获取数据
        # g.dataTrade, g.signals, g.weight_tb, g.dataBenchmark, dataFactorSrc, date_range_src, g.config = dataSrc_dict['dataTrade'], dataSrc_dict['signals'], dataSrc_dict['weight_tb'], dataSrc_dict['dataBenchmark'], dataSrc_dict['dataFactorSrc'], dataSrc_dict['date_range_src'], dataSrc_dict['config']
        g.dataTrade, g.signals, g.dataBenchmark, dataFactorSrc, date_range_src, g.config = dataSrc_dict['dataTrade'], dataSrc_dict['signals'], dataSrc_dict['dataBenchmark'], dataSrc_dict['dataFactorSrc'], dataSrc_dict['date_range_src'], dataSrc_dict['config']

    # 将context相应的属性初始化；date_range_src 日期格式化之后赋值给 context.date_range，根据context.start_date和context.end_date截取并修改context.date_range；
    backtest.init_trade_cal(context=context, date_range=date_range_src, globals=globals())
    # 输出因子生成信号结果
    g.signals.to_csv(f"result/config{context.config['config_index']}/{context.config['func_name_factor']}_g_signals_result.csv")

    # 当调用向量化计算框架时，将 交易源数据、信号源数据、基准源数据、因子权重表（可选）、因子绘图数据（可选） 保存到 上下文变量backtext中；非向量化计算不存入context，防止context持有过多数据量。
    if context.backtest_type == 'VECTOR' or context.config['multi_run_factor_security'] == "1_security_n_factor":
        # g.dataTrade、g.signals、g.dataBenchmark应为透视表或pd.Series；g.weight_tb调用因子返回的因子权重表, g.factor_plot调用因子返回的因子绘图数据字典；如有，与g.signals同步返回并分别赋值给g，然后再赋值给context，没有可以不赋值。
        # context.dataTrade, context.signals, context.weight_tb, context.dataBenchmark, context.dataFactorSrc, context.factor_plot = g.dataTrade, g.signals, g.weight_tb, g.dataBenchmark, dataFactorSrc, g.factor_plot
        context.dataTrade, context.signals, context.dataBenchmark, context.dataFactorSrc = g.dataTrade, g.signals, g.dataBenchmark, dataFactorSrc


def handle_data(context):
    """
        因子具体逻辑实现的函数，每个时刻只被调用一次，在此函数进行下单
    :param context: Context对象，因子的各种属性上下文
    """
    if len(g.signals) <= 1 or context.all_result.get('res_optimize'):     # len(g.signals) <= 1   # 因子中已做寻优计算并返回结果，pipeline中不再计算。
        return
    # 获取当前时间、当前标的价格数据
    price = g.dataTrade.loc[g.dataTrade.index == context.current_dt].iloc[0]
    signal = g.signals.loc[g.signals.index == context.current_dt, :].iloc[0]
    signal_weight = g.weight_tb.loc[g.weight_tb.index == context.current_dt, :].iloc[0]
    # signal = g.signals.loc[context.current_dt]
    # signal_weight = g.weight_tb.loc[context.current_dt]

    # 拆分各个标的的 buy1 和 sale1；
    # 取当前时间点所有标的的价格字符串，行索引转换为 ts_code    # 2026年6月9日11:07:57
    price_sc_series = g.df_dataTrade_buy1_sale1.loc[g.df_dataTrade_buy1_sale1.index == context.current_dt].iloc[0]
    # 按 "_" 拆分，并强制保留前三列    # 2026年6月2日11:21:33
    price_df = price_sc_series.str.split("_", expand=True).reindex(columns=range(3))
    # 正好有两个 "_" 时使用拆分后的三列，否则三列都使用下划线前的第一个值，最后转 float    # 2026年6月2日11:21:33
    price_df = price_df.where(price_sc_series.str.count("_").eq(2).fillna(False), price_df[0], axis=0).astype(float)
    # 将 0、1、2 三列重命名为 close、buy1、sale1    # 2026年6月9日11:07:57
    price_df.columns = ['close', 'buy1', 'sale1']

    # 卖出：分账号、分证券标的
    for i in range(1, context.subportfolio_num + 1):  # 先把不在对应组合中的标的先卖掉。
        for security_code, signal_value in signal.items():
            if not signal_value > 0 and g.security_direction_subportfolio_index.get(security_code, {}).get('long', 0) == i:
                # backtest.order_target_percent(context, security_code, price[security_code], 0, i)
                backtest.order_target_percent(context, security_code, price_df.loc[security_code, 'buy1'], 0, i)
            elif not signal_value < 0 and g.security_direction_subportfolio_index.get(security_code, {}).get('short', 0) == i:
                # backtest.order_target_percent(context, security_code, price[security_code], 0, i)
                backtest.order_target_percent(context, security_code, price_df.loc[security_code, 'sale1'], 0, i)
    # 买入：分账号、分证券标的
    for i in range(1, context.subportfolio_num + 1):  # 先把不在对应组合中的标的先卖掉。
        for security_code, signal_value in signal.items():
            if signal_value > 0 and g.security_direction_subportfolio_index.get(security_code, {}).get('long', 0) == i:
                # backtest.order_target_percent(context, security_code, price[security_code], signal_weight[security_code], i)
                backtest.order_target_percent(context, security_code, price_df.loc[security_code, 'sale1'], signal_weight[security_code], i)
            elif signal_value < 0 and g.security_direction_subportfolio_index.get(security_code, {}).get('short', 0) == i:
                # backtest.order_target_percent(context, security_code, price[security_code], signal_weight[security_code], i)
                backtest.order_target_percent(context, security_code, price_df.loc[security_code, 'buy1'], signal_weight[security_code], i)


def update_value(context, afterTrading=False):
    """
        更新每个portfolio和benchmark的价格和价值，盘前和盘后分别更新一次
    :param context: Context对象，因子的各种属性上下文
    :param afterTrading: bool, 是否是盘后更新，默认为否
    """
    # 遍历每个子账户
    for i in range(context.subportfolio_num + 1):
        # 遍历子账户中的持仓标的
        for stock in context.portfolios[i].positions_all:
            # 读取当前价格数据
            ### 方法一：
            # price = g.dataTrade.loc[(g.dataTrade.index == context.current_dt) & (g.dataTrade['ts_code'] == stock), 'close']
            # price = price.values[0] if price else 0   # 取出的price是Series对象，可能为空，
            ### 方法二：
            # price = g.dataTrade[g.dataTrade['ts_code'] == stock].loc[context.current_dt, 'close']
            # price = g.dataTrade[g.dataTrade['ts_code'] == stock].loc[context.current_dt, 'close'] if context.current_dt in g.dataTrade[g.dataTrade['ts_code'] == stock].index else None
            # price0 = g.dataTrade.query(f'ts_code=="{context.security[0]}"').loc[context.current_dt, 'close']
            ### 方法三：适用于透视表（或只有一列的单证券标的DataFrame）
            ## （1）透视表：多证券标的
            # price = g.dataTrade.loc[context.current_dt, g.dataTrade.columns.isin(['security1', 'security2'])]     # 返回Series对象
            ## （2-1）透视表：单证券标的，列名非标的名：
            # price = g.dataTrade.loc[context.current_dt, 'close']  # .loc有时候相同索引日期列无法全部输出，只能输出一个值；
            # price = g.dataTrade.loc[g.dataTrade.index == context.current_dt, 'close']  # 如果是多标的，不能获取价格，需要先筛选标的！！！
            ## （2-2）透视表：单证券标的，列名为标的名：
            # price = g.dataTrade.loc[context.current_dt, g.dataTrade.columns == stock]     # 返回Series对象
            # price = g.dataTrade.loc[context.current_dt, g.dataTrade.columns == stock].values[0]     # .values[0] [0]；返回单值，但空Series会报错。
            # price = g.dataTrade.loc[context.current_dt, stock] if stock in g.dataTrade.columns else 0     # 返回单值

            price = g.dataTrade.loc[context.current_dt, stock] if stock in g.dataTrade.columns else 0
            # 将所有指标存储为字典, 止损指标数据调用stopLoss
            attributes = {**{"price": price}}
            # 更新持仓标的的指标
            context.portfolios[i].positions_all[stock].update(current_dt=context.current_dt, attributes=attributes, afterTrading=afterTrading)
    for key in context.benchmark.keys() if context.benchmark else []:
        # 存储benchmark每个组成部分的价格
        context.benchmark_return.loc[context.current_dt, key] = g.dataBenchmark.loc[context.current_dt, key] if not pd.DataFrame(g.dataBenchmark).empty else 0
    # 更新context
    context.update(afterTrading=afterTrading)


def before_trading(context):
    """
        盘前处理函数，每天策略开始交易前会被调用，不能在这个函数中发送订单
    :param context: Context对象，因子的各种属性上下文
    """
    # 调用更新函数更新价值和价格
    update_value(context=context, afterTrading=False)


def after_trading(context):
    """
        盘后处理函数，每天收盘后会被调用，不能在这个函数中发送订单
    :param context: Context对象，因子的各种属性上下文
    """
    # 调用更新函数更新价值和价格
    update_value(context=context, afterTrading=True)



if __name__ == "__main__":
    import config_super  # 导入全局配置
    import config as config_local

    # 用传入的远端config_super中的CONFIG更新本地CONFIG
    CONF_merge = config_super.update_config(super_config=config_super.CONFIG, config_local=config_local.CONFIG_factor)
    # 生成配置组合
    configs = config_super.generate_config_combinations(CONF_merge)  # [0:2]

    result_output, multi_run_result = multi_run(config_super.CONFIG, configs, initialize, before_trading, handle_data, after_trading)
    # result_output, multi_run_result = multi_run(super_config=config_super.CONFIG, config_local=configs, initialize=initialize, before_trading=before_trading, handle_data=handle_data, after_trading=after_trading)
    # result_output, multi_run_result = multi_run(super_config=config_super.CONFIG, config_local=configs)
    # result_output, multi_run_result = multi_run(super_config={}, config_local=configs)
    # result_output, multi_run_result = multi_run({}, configs, initialize, before_trading, handle_data, after_trading)

    result_output.to_pickle('result/result.pkl')
    import pickle
    pickle.dump(multi_run_result, open("result/all_result.pkl", "wb"))

    print("done")
