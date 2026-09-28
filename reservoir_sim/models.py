"""情景与逐日数据的数据模型及校验。"""

from dataclasses import dataclass, field
import math

from .errors import InputValidationError

DEMAND_CATEGORIES = ("ecological", "domestic", "irrigation")


def _is_finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class Scenario:
    """一个命名情景的参数，水量单位均为立方米。"""

    name: str
    total_capacity: float
    initial_storage: float
    dead_storage: float
    daily_release_cap: float

    def validate(self) -> None:
        problems = []
        if not isinstance(self.name, str) or not self.name.strip():
            problems.append("情景名称必须是非空字符串")
        for field_name, label in (
            ("total_capacity", "总库容"),
            ("initial_storage", "初始蓄水"),
            ("dead_storage", "最低保留水量"),
            ("daily_release_cap", "每日放水上限"),
        ):
            value = getattr(self, field_name)
            if not _is_finite_number(value):
                problems.append(f"情景 {self.name!r} 的{label}必须是有限数值")
            elif value < 0:
                problems.append(f"情景 {self.name!r} 的{label}不能为负数")
        if problems:
            raise InputValidationError(problems)
        if self.dead_storage > self.total_capacity:
            problems.append(
                f"情景 {self.name!r} 的最低保留水量 {self.dead_storage} 超过总库容 {self.total_capacity}"
            )
        if self.initial_storage > self.total_capacity:
            problems.append(
                f"情景 {self.name!r} 的初始蓄水 {self.initial_storage} 超过总库容 {self.total_capacity}"
            )
        if self.initial_storage < 0:
            problems.append(f"情景 {self.name!r} 的初始蓄水不能为负数")
        if problems:
            raise InputValidationError(problems)


@dataclass(frozen=True)
class DailyInput:
    """某天的来水、蒸发需求和三类需水（均为立方米）。"""

    date: str
    inflow: float
    evaporation: float
    demands: tuple


@dataclass
class DayRecord:
    """逐日模拟结果，水量单位均为立方米。"""

    date: str
    storage_start: float
    inflow: float
    evaporation: float
    supplies: dict = field(default_factory=dict)
    shortages: dict = field(default_factory=dict)
    spill: float = 0.0
    storage_end: float = 0.0
    balance_residual: float = 0.0
