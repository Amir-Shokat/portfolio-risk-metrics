"""Historical portfolio risk measures with explicit eligibility statuses.

Quick use::

    from portfolio_risk import load_inputs, assess
    inputs = load_inputs("examples/daily_returns.csv", "examples/trading_days.csv", "examples/tbill_ytm.csv")
    report = assess(inputs, horizon="1Y")
    report["sharpe"].status, report["sharpe"].value
"""

from .contract import METRICS, Contract, load_contract
from .eligibility import Status
from .inputs import InputError, RiskInputs, load_inputs, make_inputs
from .report import MetricResult, RiskReport, assess

__version__ = "1.3.0"

__all__ = ["METRICS", "Contract", "InputError", "MetricResult", "RiskInputs", "RiskReport", "Status",
           "assess", "load_contract", "load_inputs", "make_inputs", "__version__"]
