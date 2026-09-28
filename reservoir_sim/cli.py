"""reservoir_sim 命令行入口。"""

import argparse
import sys

from .errors import InputValidationError
from .io import load_daily_inputs, load_scenarios
from .simulate import run_scenario
from .writers import build_summary_payload, write_daily_csv, write_summary_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reservoir-sim",
        description="水库逐日供水模拟：比较不同库容、保留水量与放水能力下的供水效果。",
    )
    parser.add_argument("--scenarios", required=True, help="情景 JSON 文件路径")
    parser.add_argument("--inputs", required=True, help="逐日输入 CSV 文件路径")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument(
        "--summary-name",
        default="summary.json",
        help="汇总 JSON 文件名（默认 summary.json）",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        scenarios = load_scenarios(args.scenarios)
        daily_inputs = load_daily_inputs(args.inputs)
    except InputValidationError as exc:
        print("输入校验失败，已整批拒绝：", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"无法读取输入文件: {exc}", file=sys.stderr)
        return 2

    results = [run_scenario(scenario, daily_inputs) for scenario in scenarios]

    daily_files = {}
    for result in results:
        name = result["scenario"].name
        filename = f"daily_{_safe_filename(name)}.csv"
        write_daily_csv(f"{args.out_dir}/{filename}", result)
        daily_files[name] = filename

    payload = build_summary_payload(results, daily_files)
    summary_path = f"{args.out_dir}/{args.summary_name}"
    write_summary_json(summary_path, payload)

    for result in results:
        summary = result["summary"]
        print(
            f"情景 {summary['name']}: {summary['days']} 天, "
            f"整体满足率 {summary['satisfaction_ratio']:.4f}, "
            f"总弃水 {summary['total_spill']:.2f} m^3, "
            f"期末蓄水 {summary['final_storage']:.2f} m^3"
        )
    print(f"汇总已写入: {summary_path}")
    return 0


def _safe_filename(name: str) -> str:
    for char in '\\/:*?"<>|':
        name = name.replace(char, "_")
    return name.strip() or "scenario"


if __name__ == "__main__":
    raise SystemExit(main())
