"""逐日水库供水模拟核心。

每日计算顺序（水量单位均为立方米）：

1. 期初蓄水加入当天来水；
2. 扣除实际蒸发，蒸发最多把蓄水扣到零（实际蒸发 <= 蒸发需求）；
3. 供水只使用超过最低保留水量的部分，按生态、生活、灌溉顺序
   逐项分配，每项不超过其需求，且三类供水合计不超过每日放水上限；
4. 分配后超过总库容的部分记为弃水，剩余蓄水为期末蓄水，进入次日。

水量平衡：期初蓄水 + 来水 = 实际蒸发 + 三类供水 + 弃水 + 期末蓄水。
"""

from __future__ import annotations

from .io import InputDay
from .models import DailyRecord, Scenario

BALANCE_TOLERANCE = 1e-7


def _allocate_supply(
    available: float,
    max_release: float,
    demands: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """按生态、生活、灌溉顺序分配可供水量。

    available 为扣除保留水量与蒸发后可用于供水的水量。
    """
    supplies: list[float] = []
    remaining_capacity = max_release
    remaining_water = max(available, 0.0)
    for demand in demands:
        amount = min(demand, remaining_water, remaining_capacity)
        supplies.append(amount)
        remaining_water -= amount
        remaining_capacity -= amount
    supply_tuple = (supplies[0], supplies[1], supplies[2])
    shortage_tuple = (
        demands[0] - supply_tuple[0],
        demands[1] - supply_tuple[1],
        demands[2] - supply_tuple[2],
    )
    return supply_tuple, shortage_tuple


def simulate(scenario: Scenario, days: list[InputDay]) -> list[DailyRecord]:
    """对单个情景从初始蓄水开始逐日模拟，返回逐日记录。"""
    ordered = sorted(days, key=lambda d: d.day)
    storage = scenario.initial_storage
    records: list[DailyRecord] = []

    for item in ordered:
        storage_start = storage

        # 1. 加入来水（此时可能超过总库容，先不弃水，统一在第 4 步处理）。
        storage += item.inflow

        # 2. 实际蒸发：最多扣到蓄水为零。
        evaporation_actual = min(item.evaporation_demand, storage)
        storage -= evaporation_actual

        # 3. 供水：只能使用超过最低保留水量的部分。
        demands = (item.eco_demand, item.domestic_demand, item.irrigation_demand)
        available = max(0.0, storage - scenario.reserve)
        supplies, shortages = _allocate_supply(available, scenario.max_release, demands)
        total_supply = supplies[0] + supplies[1] + supplies[2]
        storage -= total_supply

        # 4. 超过总库容的部分弃水；保留水量在正常情况下始终得到保证。
        spill = max(0.0, storage - scenario.total_capacity)
        storage -= spill
        storage_end = storage

        balance_residual = (
            storage_start
            + item.inflow
            - evaporation_actual
            - total_supply
            - spill
            - storage_end
        )
        if abs(balance_residual) > BALANCE_TOLERANCE:
            raise ArithmeticError(
                f"情景 {scenario.name!r} 日期 {item.day.isoformat()} 水量不平衡: "
                f"残差 {balance_residual}"
            )

        records.append(
            DailyRecord(
                date=item.day.isoformat(),
                inflow=item.inflow,
                evaporation_demand=item.evaporation_demand,
                storage_start=storage_start,
                storage_end=storage_end,
                evaporation_actual=evaporation_actual,
                eco_demand=demands[0],
                eco_supply=supplies[0],
                eco_shortage=shortages[0],
                domestic_demand=demands[1],
                domestic_supply=supplies[1],
                domestic_shortage=shortages[1],
                irrigation_demand=demands[2],
                irrigation_supply=supplies[2],
                irrigation_shortage=shortages[2],
                spill=spill,
                balance_residual=balance_residual,
            )
        )
    return records
