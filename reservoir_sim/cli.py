"""命令行入口：python -m reservoir_sim ..."""

from __future__ import annotations

import argparse
import sys

from .errors import SimulationError
from .io import read_daily_csv, read_scenarios_json
from .report import build_summary, write_daily_csv, write_summary_json
from .simulation import simulate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reservoir_sim",
        description="水库逐日供水模拟：比较不同库容、保留水量与放水能力的供水效果",
    )
    parser.add_argument("--scenarios", required=True, help="命名情景 JSON 文件路径")
    parser.add_argument("--data", required=True, help="逐日来水/蒸发/需水 CSV 文件路径")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument(
        "--summary",
        default="summary.json",
        help="汇总 JSON 文件名（相对输出目录），默认 summary.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scenarios = read_scenarios_json(args.scenarios)
        days = read_daily_csv(args.data)

        summaries = []
        for scenario in scenarios:
            records = simulate(scenario, days)
            write_daily_csv(f"{args.out_dir.rstrip('/\\')}/{scenario.name}_daily.csv", records)
            summaries.append(build_summary(scenario, records))
        write_summary_json(f"{args.out_dir.rstrip('/\\')}/{args.summary}", summaries)
    except SimulationError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"完成：{len(summaries)} 个情景结果已写入 {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
