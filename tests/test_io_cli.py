import json
import tempfile
import unittest
from pathlib import Path

from reservoir_sim.cli import main
from reservoir_sim.errors import ValidationError
from reservoir_sim.io import read_daily_csv, read_scenarios_json

HEADER = "date,inflow,evaporation_demand,eco_demand,domestic_demand,irrigation_demand\n"


class TestCSVValidation(unittest.TestCase):
    def write_csv(self, content):
        tmp = Path(self.temp_dir) / "daily.csv"
        tmp.write_text(HEADER + content, encoding="utf-8")
        return tmp

    def setUp(self):
        self._stack = tempfile.TemporaryDirectory()
        self.temp_dir = self._stack.name

    def tearDown(self):
        self._stack.cleanup()

    def test_unsorted_rows_are_sorted(self):
        path = self.write_csv(
            "2024-01-02,1,0,0,0,0\n2024-01-01,2,0,0,0,0\n"
        )
        rows = read_daily_csv(path)
        self.assertEqual([r.day.isoformat() for r in rows], ["2024-01-01", "2024-01-02"])
        self.assertEqual(rows[0].inflow, 2.0)

    def test_duplicate_date_reports_lines(self):
        path = self.write_csv(
            "2024-01-01,1,0,0,0,0\n2024-01-01,2,0,0,0,0\n"
        )
        with self.assertRaisesRegex(ValidationError, "重复.*第 2 行与第 3 行"):
            read_daily_csv(path)

    def test_missing_date_reports_gap(self):
        path = self.write_csv(
            "2024-01-01,1,0,0,0,0\n2024-01-03,2,0,0,0,0\n"
        )
        with self.assertRaisesRegex(ValidationError, "缺失.*2024-01-02"):
            read_daily_csv(path)

    def test_invalid_and_negative_numbers_rejected(self):
        path = self.write_csv("2024-01-01,nan,0,0,0,0\n")
        with self.assertRaisesRegex(ValidationError, "有限值"):
            read_daily_csv(path)
        path = self.write_csv("2024-01-01,1,-2,0,0,0\n")
        with self.assertRaisesRegex(ValidationError, "不得为负数"):
            read_daily_csv(path)
        path = self.write_csv("2024-01-01,x,0,0,0,0\n")
        with self.assertRaisesRegex(ValidationError, "不是数值"):
            read_daily_csv(path)

    def test_bad_date_and_missing_column(self):
        path = self.write_csv("01/01/2024,1,0,0,0,0\n")
        with self.assertRaisesRegex(ValidationError, "日期非法"):
            read_daily_csv(path)
        tmp = Path(self.temp_dir) / "bad.csv"
        tmp.write_text("date,inflow\n2024-01-01,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "缺少必需列"):
            read_daily_csv(tmp)


class TestScenarioValidation(unittest.TestCase):
    def setUp(self):
        self._stack = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._stack.name)

    def tearDown(self):
        self._stack.cleanup()

    def read(self, payload):
        path = self.temp_dir / "scenarios.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return read_scenarios_json(path)

    BASE = dict(total_capacity=100.0, initial_storage=50.0, reserve=10.0, max_release=20.0)

    def test_valid_mapping_and_list_forms(self):
        scenarios = self.read({"a": self.BASE})
        self.assertEqual(scenarios[0].name, "a")
        scenarios = self.read({"scenarios": [{"name": "b", **self.BASE}]})
        self.assertEqual(scenarios[0].name, "b")

    def test_reserve_above_capacity_rejected(self):
        with self.assertRaisesRegex(ValidationError, "reserve.*超过"):
            self.read({"a": {**self.BASE, "reserve": 150.0}})

    def test_initial_storage_out_of_range_rejected(self):
        with self.assertRaisesRegex(ValidationError, "initial_storage.*超出"):
            self.read({"a": {**self.BASE, "initial_storage": 101.0}})
        with self.assertRaisesRegex(ValidationError, "不得为负数"):
            self.read({"a": {**self.BASE, "initial_storage": -1.0}})

    def test_non_finite_and_missing_field(self):
        with self.assertRaisesRegex(ValidationError, "有限值"):
            self.read({"a": {**self.BASE, "max_release": float("inf")}})
        with self.assertRaisesRegex(ValidationError, "缺少字段"):
            bad = dict(self.BASE)
            del bad["reserve"]
            self.read({"a": bad})

    def test_duplicate_name_and_empty(self):
        with self.assertRaisesRegex(ValidationError, "名称重复"):
            self.read([
                {"name": "a", **self.BASE},
                {"name": "a", **self.BASE},
            ])
        with self.assertRaisesRegex(ValidationError, "未定义任何情景"):
            self.read({})


class TestCLI(unittest.TestCase):
    def setUp(self):
        self._stack = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._stack.name)

    def tearDown(self):
        self._stack.cleanup()

    def test_cli_writes_outputs_and_is_deterministic(self):
        scenarios_path = self.temp_dir / "scenarios.json"
        scenarios_path.write_text(json.dumps({"a": TestScenarioValidation.BASE}), encoding="utf-8")
        data_path = self.temp_dir / "daily.csv"
        data_path.write_text(
            HEADER
            + "2024-01-02,50,1,2,3,4\n2024-01-01,10,1,2,3,4\n",
            encoding="utf-8",
        )
        out_dir = self.temp_dir / "out"
        code = main([
            "--scenarios", str(scenarios_path),
            "--data", str(data_path),
            "--out-dir", str(out_dir),
        ])
        self.assertEqual(code, 0)
        self.assertTrue((out_dir / "a_daily.csv").exists())
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["scenarios"][0]["scenario"], "a")

        # 确定性：再跑一次结果完全一致
        out_dir2 = self.temp_dir / "out2"
        main([
            "--scenarios", str(scenarios_path),
            "--data", str(data_path),
            "--out-dir", str(out_dir2),
        ])
        self.assertEqual(
            (out_dir / "a_daily.csv").read_text(encoding="utf-8"),
            (out_dir2 / "a_daily.csv").read_text(encoding="utf-8"),
        )

    def test_cli_invalid_input_returns_one(self):
        scenarios_path = self.temp_dir / "scenarios.json"
        scenarios_path.write_text(json.dumps({"a": TestScenarioValidation.BASE}), encoding="utf-8")
        data_path = self.temp_dir / "daily.csv"
        data_path.write_text(HEADER + "2024-01-01,-1,0,0,0,0\n", encoding="utf-8")
        code = main([
            "--scenarios", str(scenarios_path),
            "--data", str(data_path),
            "--out-dir", str(self.temp_dir / "out"),
        ])
        self.assertEqual(code, 1)

    def test_scenario_order_independence(self):
        base = TestScenarioValidation.BASE
        scenarios_path = self.temp_dir / "scenarios.json"
        scenarios_path.write_text(
            json.dumps({"scenarios": [
                {"name": "b", **{**base, "max_release": 5.0}},
                {"name": "a", **base},
            ]}),
            encoding="utf-8",
        )
        data_path = self.temp_dir / "daily.csv"
        data_path.write_text(
            HEADER + "2024-01-01,10,0,10,10,10\n2024-01-02,10,0,10,10,10\n",
            encoding="utf-8",
        )
        out_dir = self.temp_dir / "out"
        main([
            "--scenarios", str(scenarios_path),
            "--data", str(data_path),
            "--out-dir", str(out_dir),
        ])
        daily_a = (out_dir / "a_daily.csv").read_text(encoding="utf-8")
        daily_b = (out_dir / "b_daily.csv").read_text(encoding="utf-8")

        scenarios_path.write_text(
            json.dumps({"scenarios": [
                {"name": "a", **base},
                {"name": "b", **{**base, "max_release": 5.0}},
            ]}),
            encoding="utf-8",
        )
        out_dir2 = self.temp_dir / "out2"
        main([
            "--scenarios", str(scenarios_path),
            "--data", str(data_path),
            "--out-dir", str(out_dir2),
        ])
        self.assertEqual(daily_a, (out_dir2 / "a_daily.csv").read_text(encoding="utf-8"))
        self.assertEqual(daily_b, (out_dir2 / "b_daily.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
