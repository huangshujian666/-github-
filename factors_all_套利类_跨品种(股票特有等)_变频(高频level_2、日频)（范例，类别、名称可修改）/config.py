# -*- coding: utf-8 -*-
# coding=utf-8
# 主要功能：本地config设置

try:
    import json
    with open("config_factor_index.json", 'r') as json_file:
        config_factor_index = json.load(json_file)
except:
    pass
# 当因子量比较大时，可以将因子放到config_factor_dict.py(需新增)中，然后通过import引入，便于因子配置项筛选、切片选择管理。同时需要修改config中赋值方式为：{"factor_dict": factor_dict}
factor_num_start = int(config_factor_index['factor_num_start']) if 'config_factor_index' in globals() else 0        # 使用 config_factor_dict.py 时，控制其因子分析起始序号
factor_num_end = int(config_factor_index['factor_num_end']) if 'config_factor_index' in globals() else 1000000      # 使用 config_factor_dict.py 时，控制其因子分析结束序号
print("********正在处理*************")
print(f"因子索引起始值: {factor_num_start}")
print(f"因子索引结束值: {factor_num_end}")
print("*********************")
try:
    import config_factor_dict
    factor_dict = config_factor_dict.factor_dict[factor_num_start:factor_num_end] if factor_num_end else config_factor_dict.factor_dict # [:1]切片筛选一部分因子执行
except:
    factor_dict = []
try:
    import config_factor_dict
    param_dataSrc = config_factor_dict.param_dataSrc
except:
    param_dataSrc = [[]] if 'param_dataSrc' not in globals() else param_dataSrc

# 本地总CONFIG
CONFIG = {
    # # ——————————全局配置项，整体策略（非各个子账号）统一配置项：——————————
    # 全局配置说明：配置项对所有子账户、所有账户类型、所有标的同时有效；不能单独指定某个单独子账户、单独账户类型、单独标的进行特定设置；
    # 动态修改方法：可以在factor_dict中重新赋值；也可以使用set_option_global(context, configs)修改；
    # 配置方法适用配置项：适用于当前位置到"分账户编号控制配置"前所有配置项；

    # 回测开始日期；支持'年-月-日'['2018-11-23']、'年-月-日 时:分:秒'['2018-11-23 11:12:13']、'年-月-日 时:分:秒.毫秒'['2018-11-23 11:12:13.12345']格式;
    "start_date": ['2018-11-22 11:12:13.12345'],
    # 回测结束日期；支持'年-月-日'['2018-11-23']、'年-月-日 时:分:秒'['2018-11-23 11:12:13']、'年-月-日 时:分:秒.毫秒'['2018-11-23 11:12:13.12345']格式;
    "end_date": ['2027-01-02'],
    # 子账户数（即分组测试的分组数量）；套利类账户数 >= “品种数*2”；
    "subportfolio_num": [12],
    # 是否设置多空子账户（多空分组）：[]中值为所在子账户的subportfolio_index（即分组的编号）；如果不设置，则值为None。
    "long": [1],  # 多头，值为对应子账号（分组）编号
    "short": [2],  # 空头，值为对应子账号（分组）编号
    # 回测基准，字典
    "benchmark": [],  # {"000300.XSHG": 1}    {"000300.XSHG": 0.7, "110044.XSHG": 0.3}
    # 数据存放路径
    "data_dir": ["data/"],
    # 源数据库离线数据路径
    "DB_dir": ["../DB_tushare/"],
    # 结果输出路径
    "output_dir": ["result/"],
    # 是否进行因子参数寻优；如果为True，则会对factor_dict中各个因子的"param_factor"进行寻优，此时，需要该字段内所有参数均为list类型（如果原来为变为list，则需要重新将所有参数都增加[]），寻优思路与通用配置项相同；
    "param_factor_search": [],  # True  False
    # 筛选因子所用的指标,值为字典dict、空；如果为空，则使用默认指标；如果键值对的值为False(空、0、None、False等)则为放弃过滤该指标；可使用键值对字典:{"portfolio_netValue_fee":0.01,"Trading_num":1,"winRate":0.01}
    "metric_filter_criteria": [{"portfolio_netValue_fee": 0.03, "Trading_num": 10, "winRate": 0.4, "portfolio_netValue_fee_train": 0.02, "Trading_num_train": 10, "winRate_train": 0.4, "portfolio_netValue_fee_test": 0, "Trading_num_test": 1, "winRate_test": 0, "win_Rate_PnL_interval_agg": 0.1, "win_Rate_interval_agg": 0.1, "profit_loss_ratio_sum_PnL_interval_agg": 0.5, "profit_loss_ratio_sum_interval_agg": 0.5, "profit_loss_ratio_mean_PnL_interval_agg": 0.5, "profit_loss_ratio_mean_interval_agg": 0.5, "expected_return_PnL_interval_agg": 0, "expected_return_interval_agg": 0}],

}


field_mapping_table = {
}


config_custom = {
    # # ——————————自定义配置项、因子配置项：——————————
    # 自定义配置项说明：因子自有配置项，只能在因子空间主动使用，不进backtest，不一定出现在远端config中。
    # 动态修改方法：可以在factor_dict中重新赋值；也可以set_option_instrument(context, conditions, ref=None)修改；

    "name": ["谢夏楠"],
    "ID": ["445221200607286814"],
    "Tel": ["15802068225"],
    "mail": ["2864757580@qq.com"],
    "organazation": ["华南理工大学"],


    # 模型文件名称，模型文件名称要使用模型本身名称来直接命名；作为import引入时使用,不带后缀；如果有相对路径，需要加上；
    # 如因子存放在"factor_xxx.py"中，则需要import该模型文件，
    "file_name_model": [],
    # 因子函数名称；可能与factor_name不止相差"_signal"，如信号为多个因子组合生成时；
    "func_name_factor": [],
    # 因子参数
    "param_factor": [],
    # 因子参数组合，每个参数可能对应一种或多种可能的选择;其内容是"param_factor"对应参数组合的更多可选项。
    # 如："param_factor": {'param1':1,'param2':[4,5],'param3':{'param31':7,'param32':[10,11]}},
    # 对应可为："param_factor_combinations": {'param1':[1,2,3],'param2':[[4,5],[42,52],[43,53]],'param3':[{'param31':7,'param32':[10,11]}, {'param31':71,'param32':[101,111]}]},
    "param_factor_combinations": [],

    # 择时类策略的信号标志；如：True：表示是择时策略，但没有指定对应信号标志，需要自动判断；[1,-1]表示指定择时信号分类为1和-1两种；
    "timing_label": [],

    # 策略方法类型;可选值:择时"timing"、选股"stockSelection"、"资产配置"、"机器学习和深度学习"、配对交易类"PairTrading"、套利类"Arbitrage"
    # "选股stockSelection"，通用称呼，该方法适用品种不限于股票，可以是用于其它证券标的，如基金、债券、期货、期权、债券、可转债、ETF等。
    "strategy_method_type": [],


    # 策略中用于交易证券标的；当交易交易与信号生成的证券标的相同是，则两者全部保存在此变量。也可以不使用该变量，自行定义变量名称来存储交易证券标的；
    # 如果为股票列表，需存放在config_universe，使用universe系列配置项调用；该配置项不识别config_universe中列表；该配置项内容不能过多，否则影响因子文件名称生成；
    # 列表的前后顺序无法完全对应于pipeline中g.dataTrade、dataFactorSrc中证券标的的前后顺序，因为每个标的数据的起始时间不同，具有更早数据的标的在dataGet_Func.py中会被优先排在更前面的位置（或透视表中靠左的位置；）；可能会影响最终数据中或透视表中标的顺序。
    "security": [],  # '002267.XSHE' '000300.XSHG', '002267.XSHE', '002268.XSHE'
    # 通用股票池，同时用于信号和交易；会提取并合并到security中；限单值，不支持list;rqalpha命名法，rqalpha中用于订阅标的的范围，也是交易标的的范围；
    "universe": [],  # "config_universe.HS300_2009"


    # 源数据文件名称
    "file_name": [],
    # 源数据文件名称
    "file_name_dataSrc": [],
    # 源数据获取函数名称,用于dataGet_DB.py中获取数据；可选项："read_file"、"query_DB"；
    # 注意：单因子套框架时必须用read_file；factor_all中优先使用query_DB（query_DB无法获取的数据再使用read_file）；
    "func_name_dataSrc": [],
    # 源数据参数，保存读取源数据的字典集；该字段内包含的参数将送入数据获取函数进行源数据的各种处理；
    # 已默认添加配置项，会将对应的原始键值对（无论是factor_dict还是CONFIG中）在因子无指定时赋值到该“源数据参数”中；
    # 默认添加配置项如下：["data_dir", "benchmark", "universe", "universe_trade", "universe_signal", "security", "security_trade", "security_signal",
    #   "strategy_type", "colName_dataSrc", "colName_derived_ref", "file_name_dataSrc", "func_name_dataSrc", "data_usage_purpose", "file_name_factor_IO", "colName_field_mapping"]
    # "param_dataSrc": param_dataSrc,     # 当将param_dataSrc整体移到config_factor_dict.py中时，此处需要将变量param_dataSrc作为值，不能是[param_dataSrc],因"param_dataSrc"为两层list，所以此处不能再有"[]"；
    # "param_dataSrc": [],
    "param_dataSrc": [[
        {"func_name_dataSrc": "read_file", "file_name_dataSrc": "2023_002266_trade_pickle4_M1_M1.bz2",
         "colName_dataSrc": ['date', {'ts_code': 'StockID'}, 'close'],
         "security": '002266.XSHE',
         "data_usage_purpose": 'signal',
         "colName_tradePrice": 'close',
         },
        # {"func_name_dataSrc": "read_file", "file_name_dataSrc": "2023_002268_trade_pickle4_M1_M1.bz2",
        #  "colName_dataSrc": ['date', {'ts_code': 'StockID'}, 'close'],
        #  "security": '002268.XSHE',
        #  # "data_usage_purpose": 'signal',
        #  "colName_tradePrice": 'close',
        #  },
        # {"func_name_dataSrc": "read_file", "file_name_dataSrc": "2023_002271_trade_pickle4_M1_M1.bz2",
        #  "colName_dataSrc": ['date', {'ts_code': 'StockID'}, 'close'],
        #  "security": '002271.XSHE',
        #  # "data_usage_purpose": 'signal',
        #  "colName_tradePrice": 'close',
        #  },
        #
        # # {"func_name_dataSrc": "query_DB",
        # #  "colName_dataSrc": [{'date': 'trade_date'}, 'ts_code', 'close'],
        # #  "security": ['002266.XSHE', '002268.XSHE', '002271.XSHE'],
        # #  "data_usage_purpose": 'trade',
        # #  "colName_tradePrice": 'close',
        # #  },
    ], ],
    # # "colName_dataSrc" 和 "colName_derived"共同构成用于因子源数据输入字段；为源数据必须直接包含的因子需要的字段；如果没有因子所需要的字段，则不启动计算该因子。
    # # # 如果此处和factor_dict中都为空，表示不限制输入字段数量，如机器学习中，输入特征数量可以不限制；
    # 支持单值、键值对构成的列表。因子需要的源数据的列名、数据字段，即可以从源数据库中直接获取到的字段；对应数据库可以直接获取的列，或通过列名映射可以直接获取的列；
    # 示例：'date','因子字段名', {'date':'trade_date'}, {'因子字段名':'源数据列名'}, {'因子字段名':{'源数据表名':'源数据字段名'}}
    # # 支持多个不同列重命名为相同列名，用于合并时使用；
    # 示例：源数据列名是不带表名的列表形式：{'因子字段名': ['源数据列名1', '源数据列名2']}、{'date': ['trade_date', 'end_date']}；（推荐使用）
    #      源数据列名是带表名的列表形式： {'因子字段名': [{'源数据表名1':'源数据列名1'}, {'源数据表名2':'源数据列名2'}]}、{'date': [{'bak_daily':'trade_date'}, {'fina_indicator':'end_date'}]}；
    #      源数据列名是带表名的字典形式：{'因子字段名': {'源数据表名1':'源数据列名1','源数据表名2':'源数据列名2'}}、{'date': {'bak_daily':'trade_date','fina_indicator':'end_date'}}；
    # # 不要轻易加源数据表名！！！源数据表名会限制因子跨品种测试；
    "colName_dataSrc": [],  # ['open', 'trade_date', 'unit_net_value']
    # 回测中使用的交易价格对应列名；该字段将作为将dataTrade转为透视表中字段values的值；
    "colName_tradePrice": [],  # 'close'
    # 回测中使用的因子信号对应列名；该字段将作为将dataFactorSrc转为透视表中字段values的值；
    "colName_tradeSignal": [],
    # 回测中使用的基准价格对应列名；
    "colName_benchmarkPrice": ['close'],
    # 数据用途：用于交易、生成信号；默认为空，为同时用于生成信号和交易；可选项：'trade', 'signal', []空值；
    "data_usage_purpose": [],
    # 列名所在数据库表的名称;获取数据时，除带有frequency的行情数据字段外，其它列名优先从如下数据库表中查找；
    "DB_tb_name": [],   # "income", ["income", "balancesheet"]
    # 源数据频率，使用dataGet_DB时必须给值（通用配置或因子私有配置）；DB_Tushare可选项["daily", "weekly", "monthly", "mins"];
    "data_frequency": ["daily"],  #

    # 窗长
    "winLen": [10],
    # 滚动窗长，用于因子结果的再次寻优
    "winLen_rolling": [],

    # 因子字典集；
    # # # 每个因子必须给出的参数如下（其它参数可自行增减）：
    # # "factor_dict": [{"func_name_factor": "因子名称、因子名称_signal", # 此处必须有
    # #                  "param_dataSrc": {"func_name_dataSrc": "read_file",    # 必须有；通用配置和此处设置，两种可都有，或至少选其一；单因子套框架使用"read_file"，factor_all使用"query_DB"!
    # #                                    "colName_dataSrc": [{'date': 'trade_date'}, 'close']},  # 必须有；通用配置和此处设置，两种可都有，或至少选其一；必须是单值或单值构成的list，不能有键值对！！！
    # #                  "param_factor": {"参数1": "参数值", "参数2": "参数值"},  # 非必须；根据因子需要可选；
    # #                  "file_name_model": ["factor_RSJ"],  # 必须有；通用配置和此处设置，两种可都有，或至少选其一；
    # #                  # 说明：在"param_dataSrc"外部的配置项，除规定的排除项外，也会默认添加到"param_dataSrc"的list中的每个集合内，并传入dataGet中供调用；
    # #                  # # 如果想让"param_dataSrc"的list中的每个字典有特有配置项，，则需要单独在该集合中单独添加或指定；
    # #                  }],
    # # "factor_dict": factor_dict,     # 当将factor_dict整体移到config_factor_dict.py中时，此处需要将变量factor_dict作为值，不能是[factor_dict],因"factor_dict"为list，所以此处不能再有"[]"；
"factor_dict": [
    {
        "func_name_factor": "resid_signal",
        "file_name_model": "factor_arbitrage",

        "param_dataSrc": [
            {
                "func_name_dataSrc": "query_DB",
                "colName_dataSrc": [
                    {"date": "trade_date"},
                    "ts_code",
                    "close",
                    "settle",
                ],
                "security": [
                    "OI1805.ZCE",
                    "Y1805.DCE",
                ],
                "dataSrc_getMode": "download",
                "colName_tradePrice": "close",
            },
        ],

        "param_factor": {
            "window": 60,
            "X": 2,
            "stop_loss_X": 3,
            "threshold_mode": "absolute",
        },

        "param_signal_search": {
            "bounds_val": [],
            "bounds": [],
            "n_calls": 1,
            "cost_slippage": [0.0002, 0.0002],
            "signal_drop_num": 0,
            "add_0_signal_flags": {
                "cutoff_time_range": "",
            },
        },

        "param_signal_search_combinations": {},

        "start_date": "2018-04-14",
        "end_date": "2018-05-07",
    },
],

}


config_trade = {
    # # ——————————交易专用配置项：——————————
    # 交易专用配置项说明：只能在模拟盘、实盘中使用的配置项，是交易中需要特别关注的内容。

}


CONFIG_factor = {**CONFIG, **config_custom, **config_trade, **field_mapping_table}


import config_super

# 生成本地 CONFIG 的 configs 列表
configs = config_super.generate_config_combinations(CONFIG_factor)

