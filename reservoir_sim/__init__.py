"""水库逐日供水模拟工具（仅使用 Python 标准库）。"""

from .errors import SimulationError, ValidationError
from .models import DailyRecord, Scenario
from .simulation import simulate

__all__ = [
    "DailyRecord",
    "Scenario",
    "SimulationError",
    "ValidationError",
    "simulate",
]

__version__ = "0.1.0"
