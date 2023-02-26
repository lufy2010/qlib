from qlib.workflow import R
from qlib.workflow.record_temp import  PortAnaRecord, SigAnaRecord
import qlib
import os

MARKET = "csi300"
BENCHMARK = "SH000300"
EXP_NAME = "tutorial_exp"
rid = "a641d7e9db034bbf9b6198e335a6b47e"
track_uri = "file:///Users/jersonliao/qlib/examples/mlruns/"

if __name__ == "__main__":
    qlib.init()

    port_analysis_config = {
        "executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        },
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {
                "signal": "<PRED>",
                "topk": 50,
                "n_drop": 5,
            },
        },
        "backtest": {
            "start_time": "2017-01-01",
            "end_time": "2020-08-01",
            "account": 100000000,
            "benchmark": BENCHMARK,
            "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        },
    }

    # backtest and analysis
    with R.start(experiment_name=EXP_NAME,experiment_id='3', recorder_id=rid,uri=track_uri, resume=True):

        # signal-based analysis
        rec = R.get_recorder()
        sar = SigAnaRecord(rec)
        sar.generate()
        
        #  portfolio-based analysis: backtest
        par = PortAnaRecord(rec, port_analysis_config, "day")
        par.generate()


