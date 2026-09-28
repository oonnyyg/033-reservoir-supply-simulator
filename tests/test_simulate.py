"""逐日模拟核心测试。"""

import math
import unittest

from reservoir_sim.errors import InputValidationError
from reservoir_sim.models import DEMAND_CATEGORIES, DailyInput, Scenario
from reservoir_sim.simulate import run_scenario


def make_day(date, inflow=0.0, evap=0.0, eco=0.0, dom=0.0, irr=0.0):
    return DailyInput(date=date, inflow=inflow, evaporation=evap, demands=(eco, dom, irr))


def check_balance(testcase, result):
    for day in result["days"]:
        outflows = day.evaporation + sum(day.supplies.values()) + day.spill
        testcase.assertAlmostEqual(
            day.storage_start + day.inflow,
            outflows + day.storage_end,
            places=9,
            msg=f"水量收支不平: {day.date}",
        )
        testcase.assertGreaterEqual(day.storage_start, -1e-12)
        testcase.assertGreaterEqual(day.storage_end, -1e-12)


class NormalSupplyTests(unittest.TestCase):
    def test_basic_supply_and_carryover(self):
        scenario = Scenario(
            name="base",
            total_capacity=1000.0,
            initial_storage=500.0,
            dead_storage=100.0,
            daily_release_cap=300.0,
        )
        days = [
            make_day("2026-01-01", inflow=200.0, eco=120.0, dom=80.0, irr=50.0),
            make_day("2026-01-02", inflow=10.0, eco=120.0, dom=80.0, irr=50.0),
        ]
        result = run_scenario(scenario, days)
        check_balance(self, result)

        first, second = result["days"]
        self.assertEqual(first.storage_start, 500.0)
        self.assertEqual(first.supplies["ecological"], 120.0)
        self.assertEqual(first.supplies["domestic"], 80.0)
        self.assertEqual(first.supplies["irrigation"], 50.0)
        self.assertEqual(first.storage_end, 500.0 + 200.0 - 250.0)

        self.assertEqual(second.storage_start, first.storage_end)
        self.assertEqual(second.spill, 0.0)

        summary = result["summary"]
        self.assertEqual(summary["days"], 2)
        self.assertEqual(summary["total_demand"], 500.0)
        self.assertEqual(summary["total_supply"], 500.0)
        self.assertAlmostEqual(summary["satisfaction_ratio"], 1.0)
        for category in DEMAND_CATEGORIES:
            self.assertEqual(summary["categories"][category]["shortage_days"], 0)

    def test_release_cap_limits_total_supply(self):
        scenario = Scenario("cap", 1000.0, 800.0, 0.0, 100.0)
        days = [make_day("2026-01-01", eco=60.0, dom=60.0, irr=60.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        day = result["days"][0]
        self.assertEqual(day.supplies["ecological"], 60.0)
        self.assertEqual(day.supplies["domestic"], 40.0)
        self.assertEqual(day.supplies["irrigation"], 0.0)
        self.assertEqual(day.shortages["domestic"], 20.0)
        self.assertEqual(day.shortages["irrigation"], 60.0)


class PriorityTests(unittest.TestCase):
    def test_ecological_first_then_domestic_then_irrigation(self):
        scenario = Scenario("priority", 1000.0, 200.0, 0.0, 1000.0)
        days = [make_day("2026-01-01", eco=100.0, dom=100.0, irr=100.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        supplies = result["days"][0].supplies
        self.assertEqual(supplies["ecological"], 100.0)
        self.assertEqual(supplies["domestic"], 100.0)
        self.assertEqual(supplies["irrigation"], 0.0)

    def test_dead_storage_is_reserved(self):
        scenario = Scenario("dead", 1000.0, 150.0, 100.0, 1000.0)
        days = [make_day("2026-01-01", eco=100.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        day = result["days"][0]
        self.assertEqual(day.supplies["ecological"], 50.0)
        self.assertEqual(day.shortages["ecological"], 50.0)
        self.assertEqual(day.storage_end, 100.0)


class DroughtTests(unittest.TestCase):
    def test_consecutive_drought_drains_available_water(self):
        scenario = Scenario("drought", 1000.0, 120.0, 20.0, 1000.0)
        days = [
            make_day("2026-01-01", dom=50.0),
            make_day("2026-01-02", dom=50.0),
            make_day("2026-01-03", dom=50.0),
        ]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        records = result["days"]
        self.assertEqual(records[0].supplies["domestic"], 50.0)
        self.assertEqual(records[1].supplies["domestic"], 50.0)
        self.assertEqual(records[2].supplies["domestic"], 0.0)
        self.assertEqual(records[2].storage_end, 20.0)
        self.assertEqual(result["summary"]["categories"]["domestic"]["shortage_days"], 1)


class SpillTests(unittest.TestCase):
    def test_full_reservoir_spills_excess(self):
        scenario = Scenario("spill", 1000.0, 900.0, 0.0, 100.0)
        days = [make_day("2026-01-01", inflow=400.0, dom=100.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        day = result["days"][0]
        self.assertEqual(day.supplies["domestic"], 100.0)
        self.assertEqual(day.spill, 200.0)
        self.assertEqual(day.storage_end, 1000.0)
        self.assertEqual(result["summary"]["total_spill"], 200.0)

    def test_spill_without_release(self):
        scenario = Scenario("spill2", 500.0, 400.0, 0.0, 0.0)
        days = [make_day("2026-01-01", inflow=200.0, eco=10.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        self.assertEqual(result["days"][0].spill, 100.0)


class EvaporationTests(unittest.TestCase):
    def test_evaporation_depletes_to_zero_no_negative_storage(self):
        scenario = Scenario("evap", 1000.0, 30.0, 0.0, 1000.0)
        days = [make_day("2026-01-01", inflow=20.0, evap=100.0, dom=10.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        day = result["days"][0]
        self.assertEqual(day.evaporation, 50.0)
        self.assertEqual(day.supplies["domestic"], 0.0)
        self.assertEqual(day.storage_end, 0.0)

    def test_evaporation_before_supply(self):
        scenario = Scenario("order", 1000.0, 100.0, 0.0, 1000.0)
        days = [make_day("2026-01-01", evap=80.0, eco=50.0)]
        result = run_scenario(scenario, days)
        check_balance(self, result)
        day = result["days"][0]
        self.assertEqual(day.evaporation, 80.0)
        self.assertEqual(day.supplies["ecological"], 20.0)
        self.assertEqual(day.storage_end, 0.0)


class SummaryTests(unittest.TestCase):
    def test_zero_demand_satisfaction_is_one(self):
        scenario = Scenario("zero", 100.0, 0.0, 0.0, 10.0)
        days = [make_day("2026-01-01"), make_day("2026-01-02")]
        result = run_scenario(scenario, days)
        self.assertEqual(result["summary"]["satisfaction_ratio"], 1.0)
        for category in DEMAND_CATEGORIES:
            self.assertEqual(result["summary"]["categories"][category]["satisfaction_ratio"], 1.0)

    def test_deterministic_and_order_independent(self):
        scenario = Scenario("det", 1000.0, 300.0, 50.0, 120.0)
        days = [
            make_day("2026-01-01", inflow=100.0, eco=40.0, dom=60.0, irr=90.0),
            make_day("2026-01-02", inflow=50.0, evap=10.0, eco=40.0, dom=60.0, irr=90.0),
            make_day("2026-01-03", inflow=700.0, eco=40.0, dom=60.0, irr=90.0),
        ]
        first = run_scenario(scenario, days)
        second = run_scenario(scenario, days)
        self.assertEqual(
            [d.storage_end for d in first["days"]],
            [d.storage_end for d in second["days"]],
        )
        check_balance(self, first)

        scenarios = [
            Scenario("a", 800.0, 200.0, 50.0, 100.0),
            Scenario("b", 1200.0, 400.0, 0.0, 200.0),
        ]
        run_a = run_scenario(scenarios[0], days)
        run_b = run_scenario(scenarios[1], days)
        run_a2 = run_scenario(scenarios[0], days)
        self.assertEqual(
            run_a["days"], run_a2["days"]
        )
        self.assertEqual(run_a["summary"]["final_storage"], 740.0)
        self.assertEqual(run_b["summary"]["final_storage"], 670.0)


class ScenarioValidationTests(unittest.TestCase):
    def test_invalid_scenarios_rejected(self):
        with self.assertRaises(InputValidationError):
            Scenario("x", math.nan, 0.0, 0.0, 0.0).validate()
        with self.assertRaises(InputValidationError):
            Scenario("x", 100.0, -1.0, 0.0, 0.0).validate()
        with self.assertRaises(InputValidationError):
            Scenario("x", 100.0, 0.0, 150.0, 0.0).validate()
        with self.assertRaises(InputValidationError):
            Scenario("x", 100.0, 150.0, 0.0, 0.0).validate()
        with self.assertRaises(InputValidationError):
            Scenario("x", 100.0, 0.0, 0.0, -5.0).validate()


if __name__ == "__main__":
    unittest.main()
