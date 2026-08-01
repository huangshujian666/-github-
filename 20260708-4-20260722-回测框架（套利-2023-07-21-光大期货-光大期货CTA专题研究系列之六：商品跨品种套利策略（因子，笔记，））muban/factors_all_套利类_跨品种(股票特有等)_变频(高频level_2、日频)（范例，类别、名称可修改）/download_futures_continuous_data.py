# -*- coding: utf-8 -*-
"""下载商品期货主力连续日线，并整理为本框架数据库使用的格式。"""

from pathlib import Path

import akshare as ak
import pandas as pd


# 1. 左侧是公开行情源使用的主力连续代码，右侧是框架使用的代码。
#    以后更换研究品种时，只需要修改这个字典。
CONTRACTS = {
    "RB0": "RB.SHF",  # 螺纹钢主力连续
    "HC0": "HC.SHF",  # 热轧卷板主力连续
}

# 2. 数据保存到模板自带的 DB_tushare/daily 目录。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "DB_tushare" / "daily"


def download_one_contract(source_code, framework_code):
    """下载一个品种，检查数据后保存为框架可读取的 pickle 文件。"""
    data = ak.futures_zh_daily_sina(symbol=source_code).copy()

    if data.empty:
        raise ValueError("{} 没有下载到行情数据。".format(source_code))

    # 3. 将公开行情源的字段名改为框架约定的字段名。
    data = data.rename(
        columns={
            "date": "trade_date",
            "volume": "vol",
            "hold": "oi",
        }
    )

    required_columns = [
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "settle",
        "vol",
        "oi",
    ]
    missing_columns = [
        column for column in required_columns if column not in data.columns
    ]
    if missing_columns:
        raise ValueError(
            "{} 缺少必要字段：{}".format(source_code, missing_columns)
        )

    # 4. 日期转换失败、重复日期或关键价格为空时直接报错，不静默删除。
    data["trade_date"] = pd.to_datetime(
        data["trade_date"], errors="raise"
    )
    duplicated_dates = data["trade_date"].duplicated(keep=False)
    if duplicated_dates.any():
        duplicate_values = data.loc[
            duplicated_dates, "trade_date"
        ].dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(
            "{} 存在重复交易日：{}".format(
                source_code, duplicate_values
            )
        )

    price_columns = ["open", "high", "low", "close", "settle"]
    if data[price_columns].isna().any().any():
        raise ValueError("{} 的关键价格字段存在空值。".format(source_code))

    # 5. 使用 Tushare 日线常见的 YYYYMMDD 日期格式，并补充框架代码。
    data["trade_date"] = data["trade_date"].dt.strftime("%Y%m%d")
    data.insert(0, "ts_code", framework_code)
    data = data[
        [
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "settle",
            "vol",
            "oi",
        ]
    ].sort_values("trade_date", ascending=False)

    # 6. 文件名规则与模板数据库一致，例如 RB.SHF -> RB_SHF.pickle。
    output_path = OUTPUT_DIR / (
        framework_code.replace(".", "_") + ".pickle"
    )
    data.to_pickle(output_path, protocol=4)

    print(
        "{}：{} 至 {}，共 {} 行，已保存到 {}".format(
            framework_code,
            data["trade_date"].min(),
            data["trade_date"].max(),
            len(data),
            output_path,
        )
    )


def main():
    """依次下载配置中的全部品种。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for source_code, framework_code in CONTRACTS.items():
        download_one_contract(source_code, framework_code)


if __name__ == "__main__":
    main()
