"""逐日供水模拟核心。

每日计算顺序（水量单位均为立方米）：

1. 期初蓄水 ``storage_start``；
2. 加入来水 ``inflow``；
3. 扣实际蒸发 ``evaporation``：蒸发最多扣到蓄水为零；
4. 供水只能动用超过最低保留水量 ``dead_storage`` 的部分，
   按生态 → 生活 → 灌溉顺序分配，单项不超过其需求，
   三类合计不超过每日放水上限 ``daily_release_cap``；
5. 超过总库容 ``total_capacity`` 的部分记为弃水 ``spill``；
6. 剩余蓄水 ``storage_end`` 进入次日。

水量收支恒等式：
``storage_start + inflow == evaporation + 三类供水合计 + spill + storage_end``。
"""

from .models import DEMAND_CATEGORIES, DayRecord, Scenario

BALANCE_TOLERANCE = 1e-6


def run_scenario(scenario: Scenario, daily_inputs) -> dict:
    """对单个情景从初始蓄水开始逐日模拟。

    返回 ``{"scenario": ..., "days": [DayRecord...], "summary": ...}``。
    情景之间互不影响；相同输入重复运行结果一致。
    """
    scenario.validate()
    storage = float(scenario.initial_storage)
    days = []

    totals_demand = {category: 0.0 for category in DEMAND_CATEGORIES}
    totals_supply = {category: 0.0 for category in DEMAND_CATEGORIES}
    shortage_days = {category: 0 for category in DEMAND_CATEGORIES}
    totals = {"inflow": 0.0, "evaporation": 0.0, "spill": 0.0}

    for day in daily_inputs:
        storage_start = storage
        storage += day.inflow

        actual_evap = min(day.evaporation, storage)
        storage -= actual_evap

        releasable = max(0.0, storage - scenario.dead_storage)
        cap_remaining = float(scenario.daily_release_cap)
        supplies = {}
        shortages = {}
        for category, demand in zip(DEMAND_CATEGORIES, day.demands):
            supply = min(demand, releasable, cap_remaining)
            supply = max(0.0, supply)
            supplies[category] = supply
            shortages[category] = demand - supply
            releasable -= supply
            cap_remaining -= supply
            storage -= supply
            totals_demand[category] += demand
            totals_supply[category] += supply
            if supply < demand:
                shortage_days[category] += 1

        spill = max(0.0, storage - scenario.total_capacity)
        storage -= spill
        storage_end = storage

        total_supply = sum(supplies.values())
        balance_residual = (
            storage_start + day.inflow - actual_evap - total_supply - spill - storage_end
        )

        days.append(
            DayRecord(
                date=day.date,
                storage_start=storage_start,
                inflow=day.inflow,
                evaporation=actual_evap,
                supplies=supplies,
                shortages=shortages,
                spill=spill,
                storage_end=storage_end,
                balance_residual=balance_residual,
            )
        )
        totals["inflow"] += day.inflow
        totals["evaporation"] += actual_evap
        totals["spill"] += spill

    category_summary = {}
    for category in DEMAND_CATEGORIES:
        demand = totals_demand[category]
        supply = totals_supply[category]
        satisfaction = 1.0 if demand == 0 else supply / demand
        category_summary[category] = {
            "total_demand": demand,
            "total_supply": supply,
            "total_shortage": demand - supply,
            "shortage_days": shortage_days[category],
            "satisfaction_ratio": satisfaction,
        }

    total_demand_all = sum(totals_demand.values())
    total_supply_all = sum(totals_supply.values())
    summary = {
        "name": scenario.name,
        "days": len(days),
        "initial_storage": float(scenario.initial_storage),
        "final_storage": storage,
        "total_inflow": totals["inflow"],
        "total_evaporation": totals["evaporation"],
        "total_spill": totals["spill"],
        "total_demand": total_demand_all,
        "total_supply": total_supply_all,
        "total_shortage": total_demand_all - total_supply_all,
        "satisfaction_ratio": 1.0 if total_demand_all == 0 else total_supply_all / total_demand_all,
        "categories": category_summary,
        "max_abs_balance_residual": max((abs(day.balance_residual) for day in days), default=0.0),
        "balance_tolerance": BALANCE_TOLERANCE,
    }
    return {"scenario": scenario, "days": days, "summary": summary}
