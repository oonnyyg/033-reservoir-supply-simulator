"""数据模型：情景与逐日记录。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import ValidationError


def _finite_nonnegative(value: object, field: str) -> float:
    """要求为有限且非负的数值，否则整批拒绝。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} 必须是数值，收到 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{field} 必须是有限值，收到 {value!r}")
    if number < 0.0:
        raise ValidationError(f"{field} 不得为负数，收到 {value!r}")
    return number


@dataclass(frozen=True)
class Scenario:
    """一个命名的水库调度情景，水量单位均为立方米。"""

    name: str
    total_capacity: float
    initial_storage: float
    reserve: float
    max_release: float

    @staticmethod
    def from_mapping(name: str, data: object) -> "Scenario":
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("情景名称必须是非空字符串")
        if not isinstance(data, dict):
            raise ValidationError(f"情景 {name!r} 的配置必须是 JSON 对象")

        def num(key: str) -> float:
            if key not in data:
                raise ValidationError(f"情景 {name!r} 缺少字段 {key!r}")
            return _finite_nonnegative(data[key], f"情景 {name!r} 的 {key}")

        total_capacity = num("total_capacity")
        initial_storage = num("initial_storage")
        reserve = num("reserve")
        max_release = num("max_release")

        if total_capacity <= 0.0:
            raise ValidationError(f"情景 {name!r} 的 total_capacity 必须为正数")
        if reserve > total_capacity:
            raise ValidationError(
                f"情景 {name!r} 的 reserve ({reserve}) 超过 total_capacity ({total_capacity})"
            )
        if initial_storage < 0.0 or initial_storage > total_capacity:
            raise ValidationError(
                f"情景 {name!r} 的 initial_storage ({initial_storage}) 超出 "
                f"[0, {total_capacity}] 范围"
            )
        return Scenario(
            name=name.strip(),
            total_capacity=total_capacity,
            initial_storage=initial_storage,
            reserve=reserve,
            max_release=max_release,
        )


@dataclass(frozen=True)
class DailyRecord:
    """逐日模拟结果，所有水量单位均为立方米。"""

    date: str
    inflow: float
    evaporation_demand: float
    storage_start: float
    storage_end: float
    evaporation_actual: float
    eco_demand: float
    eco_supply: float
    eco_shortage: float
    domestic_demand: float
    domestic_supply: float
    domestic_shortage: float
    irrigation_demand: float
    irrigation_supply: float
    irrigation_shortage: float
    spill: float
    balance_residual: float
