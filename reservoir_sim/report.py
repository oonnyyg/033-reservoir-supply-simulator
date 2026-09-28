"""汇总统计与结果文件输出。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import DailyRecord, Scenario

CATEGORIES = ("eco", "domestic", "irrigation")

DAILY_COLUMNS = (
    "date",
    "storage_start",
    "inflow",
    "evaporation_demand",
    "evaporation_actual",
    "eco_demand",
    "eco_supply",
    "eco_shortage",
    "domestic_demand",
    "domestic_supply",
    "domestic_shortage",
    "irrigation_demand",
    "irrigation_supply",
    "irrigation_shortage",
    "spill",
    "storage_end",
    "balance_residual",
)


def build_summary(scenario: Scenario, records: list[DailyRecord]) -> dict:
    """按需水类别汇总总需求、总供水、缺水与满足率。

    缺水天数指该类当天供水小于需求的天数；
    满足率 = 总供水 / 总需求，总需求为零时记为 1。
    """

    demand = {
        category: sum(getattr(record, f"{category}_demand") for record in records)
        for category in CATEGORIES
    }
    supply = {
        category: sum(getattr(record, f"{category}_supply") for record in records)
        for category in CATEGORIES
    }
    shortage = {
        category: sum(getattr(record, f"{category}_shortage") for record in records)
        for category in CATEGORIES
    }
    shortage_days = {
        category: sum(
            1 for record in records if getattr(record, f"{category}_supply")
            < getattr(record, f"{category}_demand")
        )
        for category in CATEGORIES
    }

    demand_total = sum(demand.values())
    supply_total = sum(supply.values())
    shortage_total = sum(shortage.values())
    any_shortage_days = sum(
        1
        for record in records
        if any(
            getattr(record, f"{category}_supply") < getattr(record, f"{category}_demand")
            for category in CATEGORIES
        )
    )

    category_satisfaction = {
        category: (1.0 if demand[category] == 0.0 else supply[category] / demand[category])
        for category in CATEGORIES
    }
    overall_satisfaction = 1.0 if demand_total == 0.0 else supply_total / demand_total

    total_inflow = sum(record.inflow for record in records)
    total_evaporation = sum(record.evaporation_actual for record in records)
    total_spill = sum(record.spill for record in records)

    return {
        "scenario": scenario.name,
        "days": len(records),
        "parameters": {
            "total_capacity": scenario.total_capacity,
            "initial_storage": scenario.initial_storage,
            "reserve": scenario.reserve,
            "max_release": scenario.max_release,
        },
        "total_demand": {**demand, "all": demand_total},
        "total_supply": {**supply, "all": supply_total},
        "total_shortage": {**shortage, "all": shortage_total},
        "shortage_days": {**shortage_days, "any": any_shortage_days},
        "satisfaction_rate": {**category_satisfaction, "all": overall_satisfaction},
        "water_budget": {
            "storage_start": records[0].storage_start if records else scenario.initial_storage,
            "storage_end": records[-1].storage_end if records else scenario.initial_storage,
            "inflow": total_inflow,
            "evaporation_actual": total_evaporation,
            "supply": supply_total,
            "spill": total_spill,
            "balance_residual": sum(record.balance_residual for record in records),
        },
    }


def write_daily_csv(path: str | Path, records: list[DailyRecord]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DAILY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = {column: getattr(record, column) for column in DAILY_COLUMNS}
            writer.writerow(row)


def write_summary_json(path: str | Path, summaries: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"scenarios": summaries}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
