# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import re
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import List, Iterable, Optional, Union

import fire
import pandas as pd
import baostock as bs
from loguru import logger
import akshare as ak
import csv


BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR.parent.parent))

from data_collector.base import BaseCollector, BaseRun, BaseNormalize
from data_collector.utils import get_hs_stock_symbols, get_calendar_list


class CNFinCollector(BaseCollector):
    DEFAULT_START_DATETIME_QUARTERLY = pd.Timestamp("2000-01-01")
    DEFAULT_START_DATETIME_ANNUAL = pd.Timestamp("2000-01-01")
    DEFAULT_END_DATETIME_QUARTERLY = pd.Timestamp(datetime.now() + pd.Timedelta(days=1))
    DEFAULT_END_DATETIME_ANNUAL = pd.Timestamp(datetime.now() + pd.Timedelta(days=1))

    INTERVAL_QUARTERLY = "quarterly"

    def __init__(
        self,
        save_dir: Union[str, Path],
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "quarterly",
        max_workers: int = 1,
        max_collector_count: int = 1,
        delay: int = 0,
        check_data_length: bool = False,
        limit_nums: Optional[int] = None,
        symbol_regex: Optional[str] = None,
    ):
        """
        Parameters
        ----------
        save_dir: str
            instrument save dir
        max_workers: int
            workers, default 1; Concurrent number, default is 1; when collecting data, it is recommended that max_workers be set to 1
        max_collector_count: int
            default 2
        delay: float
            time.sleep(delay), default 0
        interval: str
            freq, value from [1min, 1d], default 1d
        start: str
            start datetime, default None
        end: str
            end datetime, default None
        check_data_length: int
            check data length, if not None and greater than 0, each symbol will be considered complete if its data length is greater than or equal to this value, otherwise it will be fetched again, the maximum number of fetches being (max_collector_count). By default None.
        limit_nums: int
            using for debug, by default None
        symbol_regex: str
            symbol regular expression, by default None.
        """
        self.symbol_regex = symbol_regex
        super().__init__(
            save_dir=save_dir,
            start=start,
            end=end,
            interval=interval,
            max_workers=max_workers,
            max_collector_count=max_collector_count,
            delay=delay,
            check_data_length=check_data_length,
            limit_nums=limit_nums,
        )

    def get_instrument_list(self) -> List[str]:
        logger.info("get cn stock symbols......")
        symbols = get_hs_stock_symbols()
        if self.symbol_regex is not None:
            regex_compile = re.compile(self.symbol_regex)
            symbols = [symbol for symbol in symbols if regex_compile.match(symbol)]
            logger.info(f"get symbols: {symbols}")
        logger.info(f"get {len(symbols)} symbols.")
        return symbols

    def normalize_symbol(self, symbol: str) -> str:
        symbol, exchange = symbol.split(".")
        exchange = "sh" if exchange == "ss" else "sz"
        return f"{exchange}{symbol}"

    @staticmethod
    def get_performance_express_report_df(code: str, start_date: str, end_date: str) -> pd.DataFrame:
        column_mapping = {
            "performanceExpPubDate": "date",
            "performanceExpStatDate": "period",
            "performanceExpressROEWa": "value",
        }

        resp = bs.query_performance_express_report(code=code, start_date=start_date, end_date=end_date)
        report_list = []
        while (resp.error_code == "0") and resp.next():
            report_list.append(resp.get_row_data())
        report_df = pd.DataFrame(report_list, columns=resp.fields)
        try:
            report_df = report_df[list(column_mapping.keys())]
        except KeyError:
            return pd.DataFrame()
        report_df.rename(columns=column_mapping, inplace=True)
        report_df["field"] = "roeWa"
        report_df["value"] = pd.to_numeric(report_df["value"], errors="ignore")
        report_df["value"] = report_df["value"].apply(lambda x: x / 100.0)
        return report_df

    @staticmethod
    def get_profit_df(code: str, start_date: str, end_date: str) -> pd.DataFrame:
        column_mapping = {"pubDate": "date", "statDate": "period", "roeAvg": "value"}
        fields = bs.query_profit_data(code="sh.600519", year=2020, quarter=1).fields
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        args = [(year, quarter) for quarter in range(1, 5) for year in range(start_date.year - 1, end_date.year + 1)]
        profit_list = []
        for year, quarter in args:
            resp = bs.query_profit_data(code=code, year=year, quarter=quarter)
            while (resp.error_code == "0") and resp.next():
                if "pubDate" not in resp.fields:
                    continue
                row_data = resp.get_row_data()
                pub_date = pd.Timestamp(row_data[resp.fields.index("pubDate")])
                if start_date <= pub_date <= end_date and row_data:
                    profit_list.append(row_data)
        profit_df = pd.DataFrame(profit_list, columns=fields)
        try:
            profit_df = profit_df[list(column_mapping.keys())]
        except KeyError:
            return pd.DataFrame()
        profit_df.rename(columns=column_mapping, inplace=True)
        profit_df["field"] = "roeWa"
        profit_df["value"] = pd.to_numeric(profit_df["value"], errors="ignore")
        return profit_df

    @staticmethod
    def get_forecast_report_df(code: str, start_date: str, end_date: str) -> pd.DataFrame:
        column_mapping = {
            "profitForcastExpPubDate": "date",
            "profitForcastExpStatDate": "period",
            "value": "value",
        }
        resp = bs.query_forecast_report(code=code, start_date=start_date, end_date=end_date)
        forecast_list = []
        while (resp.error_code == "0") and resp.next():
            forecast_list.append(resp.get_row_data())
        forecast_df = pd.DataFrame(forecast_list, columns=resp.fields)
        numeric_fields = ["profitForcastChgPctUp", "profitForcastChgPctDwn"]
        try:
            forecast_df[numeric_fields] = forecast_df[numeric_fields].apply(pd.to_numeric, errors="ignore")
        except KeyError:
            return pd.DataFrame()
        forecast_df["value"] = (forecast_df["profitForcastChgPctUp"] + forecast_df["profitForcastChgPctDwn"]) / 200
        forecast_df = forecast_df[list(column_mapping.keys())]
        forecast_df.rename(columns=column_mapping, inplace=True)
        forecast_df["field"] = "YOYNI"
        return forecast_df

    def get_em_profit_df(self,code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.get_em_financial_df("profit", ak.stock_profit_sheet_by_quarterly_em, code, start_date,end_date)

    def get_em_cashflow_df(self,code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.get_em_financial_df("cashflo", ak.stock_cash_flow_sheet_by_quarterly_em, code, start_date,end_date)

    def get_em_balance_df(self,code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.get_em_financial_df("balance", ak.stock_balance_sheet_by_report_em, code, start_date, end_date)

    def get_saved_lastest_reort_date(self,symbol:str):
        instrument_path = self.save_dir.joinpath(f"{symbol}.csv")
        lreport_date = ""
        if not os.path.isfile(instrument_path):
            return lreport_date
        with open(instrument_path, newline='') as f:
            csv_reader = csv.reader(f)
            next(csv_reader) # ignore header
            row = next(csv_reader)
            lreport_date = row[0]
        return lreport_date

    @staticmethod
    def get_em_financial_df(fin_type:str,load_func, code:str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            raw_df = load_func(code)
            raw_df = raw_df[((not start_date) or raw_df["REPORT_DATE"]>=(start_date+" 00:00:00")) & 
                            ((not end_date) or raw_df["REPORT_DATE"]<=(end_date+" 00:00:00"))]
            fin_df = pd.DataFrame(columns=["date","period","field","value"])
            for field in raw_df.columns[14:]:
                df = pd.DataFrame(columns=["date","period","field","value"])
                df["date"]= raw_df["NOTICE_DATE"].str[0:10]
                df["period"]= raw_df["REPORT_DATE"].str[0:10]
                df["field"] = field
                df["value"] = pd.to_numeric(raw_df[field], errors="ignore")
                fin_df = pd.concat([fin_df,df],axis=0)
        except KeyError:
            return None
        return fin_df

    @staticmethod
    def get_growth_df(code: str, start_date: str, end_date: str) -> pd.DataFrame:
        column_mapping = {"pubDate": "date", "statDate": "period", "YOYNI": "value"}
        fields = bs.query_growth_data(code="sh.600519", year=2020, quarter=1).fields
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        args = [(year, quarter) for quarter in range(1, 5) for year in range(start_date.year - 1, end_date.year + 1)]
        growth_list = []
        for year, quarter in args:
            resp = bs.query_growth_data(code=code, year=year, quarter=quarter)
            while (resp.error_code == "0") and resp.next():
                if "pubDate" not in resp.fields:
                    continue
                row_data = resp.get_row_data()
                pub_date = pd.Timestamp(row_data[resp.fields.index("pubDate")])
                if start_date <= pub_date <= end_date and row_data:
                    growth_list.append(row_data)
        growth_df = pd.DataFrame(growth_list, columns=fields)
        try:
            growth_df = growth_df[list(column_mapping.keys())]
        except KeyError:
            return pd.DataFrame()
        growth_df.rename(columns=column_mapping, inplace=True)
        growth_df["field"] = "YOYNI"
        growth_df["value"] = pd.to_numeric(growth_df["value"], errors="ignore")
        
        return growth_df

    def get_data(
        self,
        symbol: str,
        interval: str,
        start_datetime: pd.Timestamp,
        end_datetime: pd.Timestamp,
    ) -> pd.DataFrame:
        if interval != self.INTERVAL_QUARTERLY:
            raise ValueError(f"cannot support {interval}")

        start_date = start_datetime.strftime("%Y-%m-%d")
        end_date = end_datetime.strftime("%Y-%m-%d")

        #symbol, exchange = symbol.split(".")
        #exchange = "sh" if exchange == "ss" else "sz"
        #bscode = f"{exchange}.{symbol}"
        #performance_express_report_df = self.get_performance_express_report_df(code, start_date, end_date)
        #profit_df = self.get_profit_df(code, start_date, end_date)
        #forecast_report_df = self.get_forecast_report_df(code, start_date, end_date)
        #growth_df = self.get_growth_df(code, start_date, end_date)

        symbol = self.normalize_symbol(symbol)
        logger.info(f"loading data for {symbol}...")
        lreport_date = self.get_saved_lastest_reort_date(symbol)
        if lreport_date:
            logger.info(f"data already loaded for {symbol}...")
            return None
        get_em_profit_df =self.get_em_profit_df(symbol, start_date, end_date)
        if get_em_profit_df is None:
            return pd.DataFrame()
        get_em_cashflow_df =self.get_em_cashflow_df(symbol, start_date, end_date)
        if get_em_cashflow_df is None:
            return pd.DataFrame()
        get_em_balance_df =self.get_em_balance_df(symbol, start_date, end_date)
        if get_em_balance_df is None:
            return pd.DataFrame()        
        df = pd.concat(
            [get_em_profit_df, get_em_cashflow_df, get_em_balance_df],
            axis=0,
        )
        return df


class CNFinNormalize(BaseNormalize):
    def __init__(self, interval: str = "quarterly", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interval = interval

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        dt = df["period"].apply(
            lambda x: (
                pd.to_datetime(x) + pd.DateOffset(days=(45 if self.interval == CNFinCollector.INTERVAL_QUARTERLY else 90))
            ).date()
        )
        df["date"] = df["date"].fillna(dt.astype(str))

        df["period"] = pd.to_datetime(df["period"])
        df["period"] = df["period"].apply(
            lambda x: x.year if self.interval == CNFinCollector.INTERVAL_ANNUAL else x.year * 100 + (x.month - 1) // 3 + 1
        )
        return df

    def _get_calendar_list(self) -> Iterable[pd.Timestamp]:
        return get_calendar_list()


class Run(BaseRun):
    @property
    def collector_class_name(self) -> str:
        return f"CNFinCollector"

    @property
    def normalize_class_name(self) -> str:
        return f"CNFinNormalize"

    @property
    def default_base_dir(self) -> Union[Path, str]:
        return BASE_DIR


if __name__ == "__main__":
   # bs.login()
    fire.Fire(Run)
  #  bs.logout()