#  Copyright (c) Microsoft Corporation.
#  Licensed under the MIT License.
"""
Qlib provides two kinds of interfaces. 
(1) Users could define the Quant research workflow by a simple configuration.
(2) Qlib is designed in a modularized way and supports creating research workflow by code just like building blocks.

The interface of (1) is `qrun XXX.yaml`.  The interface of (2) is script like this, which nearly does the same thing as `qrun XXX.yaml`
"""
import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord
from qlib.tests.data import GetData
from qlib.tests.config import CSI300_BENCH, CSI300_GBDT_TASK


def port_analysis(dataset, model, hold_thresh):
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
                "signal": (model, dataset),
                "topk": 50,
                "n_drop": 5,
                "hold_thresh": hold_thresh,
            },
        },
        "backtest": {
            "start_time": "2017-01-01",
            "end_time": "2020-08-01",
            "account": 100000000,
            "benchmark": CSI300_BENCH,
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
    # backtest
    with R.start(experiment_name="experiment"):
        R.log_params(**flatten_dict(CSI300_GBDT_TASK))
        model.fit(dataset)
        # prediction
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()
        par = PortAnaRecord(recorder, port_analysis_config, "day")
        par.generate()
    return recorder.id


def train_and_backtest():
    # train
    with R.start(experiment_name="experiment"):
        R.log_params(**flatten_dict(CSI300_GBDT_TASK))
        model.fit(dataset)

    rid1 = port_analysis(dataset, model, 1)
    rid20 = port_analysis(dataset, model, 20)
    print(rid1)
    print(rid20)
    return [rid1, rid20]


if __name__ == "__main__":

    # use default data
    provider_uri = "~/.qlib/qlib_data/cn_data"  # target_dir
    GetData().qlib_data(target_dir=provider_uri, region=REG_CN, exists_skip=True)
    qlib.init(provider_uri=provider_uri, region=REG_CN)

    #model = init_instance_by_config(CSI300_GBDT_TASK["model"])
    #dataset = init_instance_by_config(CSI300_GBDT_TASK["dataset"])

    #rid_list = train_and_backtest()
    rid_list = ["e038f77a14b14dcda091495c60fd2794","db1fb2ddaada4e30aa6aec1bda08f966"]

    report_df_map = {}
    for idx, rid in enumerate(rid_list):
        recorder = R.get_recorder(recorder_id=rid, experiment_name="experiment")
        report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        report_df_map[f"{idx}"] = report_df
