"""Reservoir daily water supply simulator.

仅使用 Python 标准库。核心入口：

- :func:`reservoir_sim.simulate.run_scenario`：运行单个情景
- :func:`reservoir_sim.cli.main`：命令行入口
"""

from .simulate import DayRecord, Scenario, run_scenario

__all__ = ["DayRecord", "Scenario", "run_scenario"]
__version__ = "0.1.0"
