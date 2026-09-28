"""输入校验、日期检查与命令行集成测试。"""

import csv
import json
import os
import tempfile
import unittest

from reservoir_sim.cli import main
from reservoir_sim.errors import InputValidationError
from reservoir_sim.io import load_daily_inputs, load_scenarios


CSV_HEADER = "date,inflow,evaporation,ecological_demand,domestic_demand,irrigation_demand"


class FileFixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return path

    def close(self):
        self.tmp.cleanup()


class DateValidationTests(unittest.TestCase):
    def setUp(self):
        self.fx = FileFixture()

    def tearDown(self):
        self.fx.close()

    def test_unsorted_rows_are_sorted(self):
        content = "\n".join(
            [CSV_HEADER, "2026-01-03,10,0,0,0,0", "2026-01-01,10,0,0,0,0", "2026-01-02,10,0,0,0,0", ""]
        )
        path = self.fx.write("in.csv", content)
        rows = load_daily_inputs(path)
        self.assertEqual([r.date for r in rows], ["2026-01-01", "2026-01-02", "2026-01-03"])

    def test_duplicate_dates_report_positions(self):
        content = "\n".join(
            [CSV_HEADER, "2026-01-01,10,0,0,0,0", "2026-01-02,10,0,0,0,0", "2026-01-01,10,0,0,0,0", ""]
        )
        path = self.fx.write("dup.csv", content)
        with self.assertRaises(InputValidationError) as ctx:
            load_daily_inputs(path)
        message = str(ctx.exception)
        self.assertIn("2026-01-01", message)
        self.assertIn("第 2 行", message)
        self.assertIn("第 4 行", message)

    def test_missing_dates_report_gap(self):
        content = "\n".join([CSV_HEADER, "2026-01-01,10,0,0,0,0", "2026-01-04,10,0,0,0,0", ""])
        path = self.fx.write("gap.csv", content)
        with self.assertRaises(InputValidationError) as ctx:
            load_daily_inputs(path)
        message = str(ctx.exception)
        for missing in ("2026-01-02", "2026-01-03"):
            self.assertIn(missing, message)

    def test_illegal_values_batch_rejected(self):
        content = "\n".join(
            [
                CSV_HEADER,
                "2026-01-01,10,0,0,0,0",
                "2026-01-02,-5,0,0,0,0",
                "not-a-date,10,0,0,0,0",
                "2026-01-04,10,abc,0,0,0",
                "",
            ]
        )
        path = self.fx.write("bad.csv", content)
        with self.assertRaises(InputValidationError) as ctx:
            load_daily_inputs(path)
        problems = ctx.exception.problems
        self.assertTrue(any("-5" in p for p in problems))
        self.assertTrue(any("not-a-date" in p for p in problems))
        self.assertTrue(any("abc" in p for p in problems))

    def test_missing_column_rejected(self):
        path = self.fx.write("no_col.csv", "date,inflow\n2026-01-01,10\n")
        with self.assertRaises(InputValidationError):
            load_daily_inputs(path)


class ScenarioLoadingTests(unittest.TestCase):
    def setUp(self):
        self.fx = FileFixture()

    def tearDown(self):
        self.fx.close()

    def test_loads_named_scenarios(self):
        path = self.fx.write(
            "s.json",
            json.dumps(
                {
                    "scenarios": [
                        {
                            "name": "small",
                            "total_capacity": 500,
                            "initial_storage": 200,
                            "dead_storage": 50,
                            "daily_release_cap": 100,
                        }
                    ]
                }
            ),
        )
        scenarios = load_scenarios(path)
        self.assertEqual(scenarios[0].name, "small")

    def test_invalid_scenarios_batch_rejected(self):
        path = self.fx.write(
            "bad.json",
            json.dumps(
                [
                    {"name": "a", "total_capacity": 100, "initial_storage": 200,
                     "dead_storage": 0, "daily_release_cap": 10},
                    {"name": "b", "total_capacity": 100, "initial_storage": 0,
                     "dead_storage": 150, "daily_release_cap": 10},
                ]
            ),
        )
        with self.assertRaises(InputValidationError) as ctx:
            load_scenarios(path)
        self.assertTrue(any("'a'" in p for p in ctx.exception.problems))
        self.assertTrue(any("'b'" in p for p in ctx.exception.problems))

    def test_duplicate_names_rejected(self):
        path = self.fx.write(
            "dup.json",
            json.dumps(
                [
                    {"name": "x", "total_capacity": 100, "initial_storage": 0,
                     "dead_storage": 0, "daily_release_cap": 10},
                    {"name": "x", "total_capacity": 100, "initial_storage": 0,
                     "dead_storage": 0, "daily_release_cap": 10},
                ]
            ),
        )
        with self.assertRaises(InputValidationError):
            load_scenarios(path)


class CliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fx = FileFixture()

    def tearDown(self):
        self.fx.close()

    def test_end_to_end_outputs(self):
        scenarios_path = self.fx.write(
            "scenarios.json",
            json.dumps(
                [
                    {"name": "small", "total_capacity": 500, "initial_storage": 200,
                     "dead_storage": 50, "daily_release_cap": 100},
                    {"name": "big", "total_capacity": 2000, "initial_storage": 800,
                     "dead_storage": 0, "daily_release_cap": 300},
                ]
            ),
        )
        inputs_path = self.fx.write(
            "inputs.csv",
            "\n".join(
                [
                    CSV_HEADER,
                    "2026-01-02,600,20,50,80,200",
                    "2026-01-01,100,10,50,80,200",
                    "2026-01-03,0,5,50,80,200",
                    "",
                ]
            ),
        )
        out_dir = os.path.join(self.fx.dir, "out")
        exit_code = main(
            ["--scenarios", scenarios_path, "--inputs", inputs_path, "--out-dir", out_dir]
        )
        self.assertEqual(exit_code, 0)

        for filename in ("daily_small.csv", "daily_big.csv", "summary.json"):
            self.assertTrue(os.path.exists(os.path.join(out_dir, filename)))

        with open(os.path.join(out_dir, "daily_small.csv"), encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([r["date"] for r in rows], ["2026-01-01", "2026-01-02", "2026-01-03"])
        for row in rows:
            start = float(row["storage_start"])
            end = float(row["storage_end"])
            outflows = (
                float(row["evaporation"])
                + float(row["total_supply"])
                + float(row["spill"])
            )
            self.assertAlmostEqual(start + float(row["inflow"]), outflows + end, places=9)

        with open(os.path.join(out_dir, "summary.json"), encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(summary["scenario_count"], 2)
        names = [item["name"] for item in summary["scenarios"]]
        self.assertEqual(names, ["small", "big"])
        for entry in summary["scenarios"]:
            self.assertLessEqual(entry["max_abs_balance_residual"], entry["balance_tolerance"])
            self.assertIn("categories", entry)

    def test_invalid_input_returns_error_code(self):
        scenarios_path = self.fx.write(
            "scenarios.json",
            json.dumps(
                [{"name": "x", "total_capacity": 100, "initial_storage": 0,
                  "dead_storage": 0, "daily_release_cap": 10}]
            ),
        )
        inputs_path = self.fx.write(
            "inputs.csv",
            "\n".join([CSV_HEADER, "2026-01-01,-1,0,0,0,0", ""]),
        )
        out_dir = os.path.join(self.fx.dir, "out")
        exit_code = main(
            ["--scenarios", scenarios_path, "--inputs", inputs_path, "--out-dir", out_dir]
        )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
