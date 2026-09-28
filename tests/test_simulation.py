import unittest

from reservoir_sim.io import InputDay
from reservoir_sim.models import Scenario
from reservoir_sim.report import build_summary
from reservoir_sim.simulation import simulate


def make_day(day, inflow=0.0, evaporation_demand=0.0, eco=0.0, domestic=0.0, irrigation=0.0):
    from datetime import date

    return InputDay(
        day=date.fromisoformat(day),
        line_no=0,
        inflow=inflow,
        evaporation_demand=evaporation_demand,
        eco_demand=eco,
        domestic_demand=domestic,
        irrigation_demand=irrigation,
    )


def base_scenario(**overrides):
    params = dict(
        name="s",
        total_capacity=100.0,
        initial_storage=50.0,
        reserve=10.0,
        max_release=20.0,
    )
    params.update(overrides)
    return Scenario(**params)


class TestSimulation(unittest.TestCase):
    def test_normal_supply_and_balance(self):
        days = [make_day("2024-01-01", inflow=30.0, eco=5.0, domestic=8.0, irrigation=4.0)]
        records = simulate(base_scenario(), days)
        record = records[0]
        self.assertEqual(record.storage_start, 50.0)
        self.assertEqual(record.eco_supply, 5.0)
        self.assertEqual(record.domestic_supply, 8.0)
        self.assertEqual(record.irrigation_supply, 4.0)
        self.assertEqual(record.storage_end, 63.0)
        self.assertEqual(record.spill, 0.0)
        self.assertAlmostEqual(record.balance_residual, 0.0)

    def test_drought_shortage_never_negative_storage(self):
        days = [
            make_day("2024-01-01", inflow=0.0, evaporation_demand=5.0, eco=30.0, domestic=30.0),
            make_day("2024-01-02", inflow=0.0, evaporation_demand=5.0, eco=30.0, domestic=30.0),
        ]
        records = simulate(base_scenario(initial_storage=40.0, reserve=10.0, max_release=100.0), days)
        self.assertEqual(records[0].storage_end, 10.0)
        self.assertEqual(records[0].eco_supply, 25.0)
        self.assertEqual(records[0].eco_shortage, 5.0)
        self.assertEqual(records[0].domestic_supply, 0.0)
        self.assertEqual(records[1].storage_end, 5.0)
        self.assertEqual(records[1].eco_supply, 0.0)
        for record in records:
            self.assertGreaterEqual(record.storage_end, 0.0)
            self.assertAlmostEqual(record.balance_residual, 0.0)

    def test_spill_when_full(self):
        days = [make_day("2024-01-01", inflow=100.0, eco=5.0)]
        record = simulate(base_scenario(), days)[0]
        # 50 + 100 - 5(供水) = 145，库容 100，弃水 45
        self.assertEqual(record.spill, 45.0)
        self.assertEqual(record.storage_end, 100.0)
        self.assertAlmostEqual(record.balance_residual, 0.0)

    def test_evaporation_drains_to_zero(self):
        days = [make_day("2024-01-01", inflow=0.0, evaporation_demand=80.0)]
        record = simulate(base_scenario(initial_storage=30.0, reserve=0.0), days)[0]
        self.assertEqual(record.evaporation_actual, 30.0)
        self.assertEqual(record.storage_end, 0.0)
        self.assertAlmostEqual(record.balance_residual, 0.0)

    def test_priority_eco_domestic_irrigation(self):
        days = [make_day("2024-01-01", inflow=0.0, eco=20.0, domestic=20.0, irrigation=20.0)]
        record = simulate(base_scenario(initial_storage=50.0, reserve=0.0, max_release=30.0), days)[0]
        self.assertEqual(record.eco_supply, 20.0)
        self.assertEqual(record.domestic_supply, 10.0)
        self.assertEqual(record.irrigation_supply, 0.0)
        self.assertEqual(
            record.eco_supply + record.domestic_supply + record.irrigation_supply, 30.0
        )

    def test_max_release_caps_total_supply(self):
        days = [make_day("2024-01-01", inflow=100.0, eco=5.0, domestic=5.0, irrigation=5.0)]
        record = simulate(base_scenario(max_release=8.0), days)[0]
        total = record.eco_supply + record.domestic_supply + record.irrigation_supply
        self.assertEqual(total, 8.0)
        self.assertEqual(record.eco_supply, 5.0)
        self.assertEqual(record.domestic_supply, 3.0)
        self.assertEqual(record.irrigation_supply, 0.0)

    def test_supply_cannot_touch_reserve(self):
        days = [make_day("2024-01-01", inflow=0.0, eco=100.0)]
        record = simulate(base_scenario(initial_storage=30.0, reserve=20.0, max_release=100.0), days)[0]
        self.assertEqual(record.eco_supply, 10.0)
        self.assertEqual(record.storage_end, 20.0)

    def test_carryover_across_days(self):
        days = [
            make_day("2024-01-02", inflow=10.0),
            make_day("2024-01-01", inflow=5.0),
        ]
        records = simulate(base_scenario(), days)
        self.assertEqual([r.date for r in records], ["2024-01-01", "2024-01-02"])
        self.assertEqual(records[0].storage_end, 55.0)
        self.assertEqual(records[1].storage_start, 55.0)
        self.assertEqual(records[1].storage_end, 65.0)


class TestSummary(unittest.TestCase):
    def test_summary_totals_and_satisfaction(self):
        days = [
            make_day("2024-01-01", inflow=10.0, eco=10.0, domestic=5.0, irrigation=10.0),
            make_day("2024-01-02", inflow=0.0, eco=10.0, domestic=5.0, irrigation=10.0),
        ]
        scenario = base_scenario(initial_storage=60.0, reserve=0.0, max_release=15.0)
        records = simulate(scenario, days)
        summary = build_summary(scenario, records)
        self.assertEqual(summary["days"], 2)
        self.assertEqual(summary["total_demand"]["eco"], 20.0)
        self.assertEqual(summary["total_demand"]["domestic"], 10.0)
        self.assertEqual(summary["total_supply"]["eco"], 20.0)
        self.assertEqual(summary["shortage_days"]["eco"], 0)
        self.assertEqual(summary["shortage_days"]["irrigation"], 2)
        self.assertEqual(summary["shortage_days"]["domestic"], 0)
        self.assertLess(summary["satisfaction_rate"]["irrigation"], 1.0)
        self.assertEqual(summary["satisfaction_rate"]["domestic"], 1.0)
        self.assertAlmostEqual(
            summary["satisfaction_rate"]["all"],
            summary["total_supply"]["all"] / summary["total_demand"]["all"],
        )

    def test_zero_demand_satisfaction_is_one(self):
        scenario = base_scenario()
        records = simulate(scenario, [make_day("2024-01-01", inflow=5.0)])
        summary = build_summary(scenario, records)
        self.assertEqual(summary["satisfaction_rate"]["all"], 1.0)
        self.assertEqual(summary["shortage_days"]["any"], 0)


if __name__ == "__main__":
    unittest.main()
