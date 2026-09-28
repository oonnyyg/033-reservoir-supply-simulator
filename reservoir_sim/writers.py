"""输出各情景逐日 CSV 与汇总 JSON。"""

import csv
import json
import os

from .models import DEMAND_CATEGORIES


DAILY_HEADER = (
    ["date", "storage_start", "inflow", "evaporation"]
    + [f"{c}_supply" for c in DEMAND_CATEGORIES]
    + [f"{c}_shortage" for c in DEMAND_CATEGORIES]
    + ["total_supply", "total_shortage", "spill", "storage_end", "balance_residual"]
)


def write_daily_csv(path: str, result: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DAILY_HEADER)
        for day in result["days"]:
            total_supply = sum(day.supplies.values())
            total_shortage = sum(day.shortages.values())
            writer.writerow(
                [day.date, day.storage_start, day.inflow, day.evaporation]
                + [day.supplies[c] for c in DEMAND_CATEGORIES]
                + [day.shortages[c] for c in DEMAND_CATEGORIES]
                + [total_supply, total_shortage, day.spill, day.storage_end, day.balance_residual]
            )


def build_summary_payload(results, daily_files: dict | None = None) -> dict:
    scenarios = []
    for result in results:
        scenario = result["scenario"]
        entry = dict(result["summary"])
        entry["parameters"] = {
            "total_capacity": scenario.total_capacity,
            "initial_storage": scenario.initial_storage,
            "dead_storage": scenario.dead_storage,
            "daily_release_cap": scenario.daily_release_cap,
        }
        if daily_files and scenario.name in daily_files:
            entry["daily_csv"] = daily_files[scenario.name]
        scenarios.append(entry)
    return {"scenario_count": len(scenarios), "scenarios": scenarios}


def write_summary_json(path: str, payload: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
