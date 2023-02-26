from sqlalchemy import create_engine
import pandas as pd
import fire
import os
import sys
from loguru import logger
from tqdm import tqdm
from concurrent.futures import  ProcessPoolExecutor
from functools import partial

from pathlib import Path
CUR_DIR = Path(__file__).resolve().parent
sys.path.append(str(CUR_DIR.parent.parent))

from data_collector.base import Normalize
from data_collector.yahoo import collector as yahoo_collector
from dump_bin import DumpDataAll

BASE_DIR="~/.qlib/qlib_data"

SRC_DIR = Path(BASE_DIR+"/source/cn_data").expanduser().absolute()
SRC_DIR.mkdir(exist_ok=True, parents=True)

SRCNOR_DIR = Path(BASE_DIR+"/source_nor/cn_data").expanduser().absolute()
SRCNOR_DIR.mkdir(exist_ok=True, parents=True)

QLIB_DIR = Path(BASE_DIR+"/cn_data").expanduser().absolute()


def crowd_dump_bin():
    dumper = DumpDataAll(csv_path=SRCNOR_DIR,qlib_dir=QLIB_DIR,
                freq="day",exclude_fields="date,symbol",date_field_name="tradedate")
    dumper()


class CrowdSourceNormalize(yahoo_collector.YahooNormalizeCN1d):
  # Add vwap so that vwap will be adjusted during normalization
  COLUMNS = ["open", "close", "high", "low", "vwap", "volume"]

  def _manual_adj_data(self, df: pd.DataFrame) -> pd.DataFrame:
    # amount should be kept as original value, so that adjusted volume * adjust vwap = amount
    result_df = super()._manual_adj_data(df)
    result_df["amount"] = df["amount"]
    return result_df

def crowd_normalize(max_workers=1, date_field_name="tradedate", symbol_field_name="symbol"):
    yc = Normalize(
        source_dir=SRC_DIR,
        target_dir=SRCNOR_DIR,
        normalize_class=CrowdSourceNormalize,
        max_workers=max_workers,
        date_field_name=date_field_name,
        symbol_field_name=symbol_field_name,
    )
    yc.normalize()

def dump_csv_one(db_connection,skip_exists,symbol):
    filename = f'{SRC_DIR}/{symbol}.csv'
    if skip_exists and os.path.isfile(filename):
        return
    stock_df = pd.read_sql("select *, amount/volume*10 as vwap from final_a_stock_eod_price "\
                            f"where symbol='{symbol}'", db_connection)
    stock_df.to_csv(filename, index=False)

def crowd_dump_csv(skip_exists=True,max_workers=1):
    sql_engine = create_engine('mysql+pymysql://root:@127.0.0.1/investment_data', pool_recycle=3600)
    db_connection = sql_engine.connect()
    universe = pd.read_sql("select symbol from final_a_stock_eod_price group by symbol", db_connection)
    with tqdm(total=len(universe)) as p_bar:
        for symbol in universe["symbol"]:
            dump_csv_one(db_connection=db_connection,skip_exists=skip_exists,symbol=symbol)
            p_bar.update()


if __name__ == "__main__":
    fire.Fire({"dump_bin": crowd_dump_bin, "normalize": crowd_normalize, "dump_csv": crowd_dump_csv})