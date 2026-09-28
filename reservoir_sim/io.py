"""输入读取：情景 JSON 与逐日数据 CSV，含严格校验。"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .errors import ValidationError
from .models import Scenario

CSV_REQUIRED_COLUMNS = (
    "date",
    "inflow",
    "evaporation_demand",
    "eco_demand",
    "domestic_demand",
    "irrigation_demand",
)


@dataclass(frozen=True)
class InputDay:
    """CSV 中一天的输入数据（行号为 CSV 文件中的物理行号，含表头）。"""

    day: date
    line_no: int
    inflow: float
    evaporation_demand: float
    eco_demand: float
    domestic_demand: float
    irrigation_demand: float


def _read_number(raw: str, field: str, line_no: int) -> float:
    text = (raw or "").strip()
    if text == "":
        raise ValidationError(f"CSV 第 {line_no} 行字段 {field!r} 为空")
    try:
        value = float(text)
    except ValueError as exc:
        raise ValidationError(
            f"CSV 第 {line_no} 行字段 {field!r} 不是数值: {text!r}"
        ) from exc
    if not math.isfinite(value):
        raise ValidationError(
            f"CSV 第 {line_no} 行字段 {field!r} 必须是有限值: {text!r}"
        )
    if value < 0.0:
        raise ValidationError(
            f"CSV 第 {line_no} 行字段 {field!r} 不得为负数: {text!r}"
        )
    return value


def read_daily_csv(path: str | Path) -> list[InputDay]:
    """读取并校验逐日 CSV，返回按日期排序后的记录。

    允许日期乱序（排序后模拟）；重复日期或日期不按天连续时，
    报错信息指出具体日期与所在 CSV 行号，非法输入整批拒绝。
    """
    path = Path(path)
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ValidationError(f"无法读取 CSV 文件 {path}: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValidationError(f"CSV 文件 {path} 缺少表头")
        missing_columns = [c for c in CSV_REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing_columns:
            raise ValidationError(
                f"CSV 文件 {path} 缺少必需列: {', '.join(missing_columns)}"
            )

        rows: list[InputDay] = []
        seen: dict[date, int] = {}
        for raw_row in reader:
            line_no = reader.line_num
            if raw_row.get("date") is None:
                raise ValidationError(f"CSV 第 {line_no} 行列数与表头不一致")
            date_text = (raw_row["date"] or "").strip()
            if date_text == "":
                raise ValidationError(f"CSV 第 {line_no} 行 date 为空")
            try:
                parsed = date.fromisoformat(date_text)
            except ValueError as exc:
                raise ValidationError(
                    f"CSV 第 {line_no} 行日期非法（应为 YYYY-MM-DD）: {date_text!r}"
                ) from exc
            if parsed in seen:
                raise ValidationError(
                    f"CSV 日期 {parsed.isoformat()} 重复：第 {seen[parsed]} 行与第 {line_no} 行"
                )
            seen[parsed] = line_no
            rows.append(
                InputDay(
                    day=parsed,
                    line_no=line_no,
                    inflow=_read_number(raw_row["inflow"], "inflow", line_no),
                    evaporation_demand=_read_number(
                        raw_row["evaporation_demand"], "evaporation_demand", line_no
                    ),
                    eco_demand=_read_number(raw_row["eco_demand"], "eco_demand", line_no),
                    domestic_demand=_read_number(
                        raw_row["domestic_demand"], "domestic_demand", line_no
                    ),
                    irrigation_demand=_read_number(
                        raw_row["irrigation_demand"], "irrigation_demand", line_no
                    ),
                )
            )

    if not rows:
        raise ValidationError(f"CSV 文件 {path} 没有任何数据行")

    rows.sort(key=lambda r: r.day)
    for previous, current in zip(rows, rows[1:]):
        gap = (current.day - previous.day).days
        if gap > 1:
            missing = [
                (previous.day + timedelta(days=offset)).isoformat()
                for offset in range(1, gap)
            ]
            raise ValidationError(
                f"CSV 日期不连续：{previous.day.isoformat()}（第 {previous.line_no} 行）"
                f"与 {current.day.isoformat()}（第 {current.line_no} 行）之间缺失 "
                f"{gap - 1} 天: {', '.join(missing)}"
            )
    return rows


def _normalize_scenario_collection(payload: object, path: Path) -> list[Scenario]:
    if isinstance(payload, dict) and isinstance(payload.get("scenarios"), (dict, list)):
        payload = payload["scenarios"]

    items: list[tuple[str, object]] = []
    if isinstance(payload, dict):
        items = list(payload.items())
    elif isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict) or "name" not in entry:
                raise ValidationError(
                    f"情景 JSON {path} 的 scenarios 列表每项必须是含 name 字段的对象"
                )
            items.append((str(entry["name"]), entry))
    else:
        raise ValidationError(
            f"情景 JSON {path} 顶层必须是情景映射、情景列表或含 scenarios 键的对象"
        )

    if not items:
        raise ValidationError(f"情景 JSON {path} 未定义任何情景")

    scenarios: list[Scenario] = []
    seen_names: set[str] = set()
    for name, config in items:
        scenario = Scenario.from_mapping(name, config)
        if scenario.name in seen_names:
            raise ValidationError(f"情景名称重复: {scenario.name!r}")
        seen_names.add(scenario.name)
        scenarios.append(scenario)
    return scenarios


def read_scenarios_json(path: str | Path) -> list[Scenario]:
    """读取多个命名情景并做完整校验。"""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ValidationError(f"无法读取情景 JSON 文件 {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"情景 JSON {path} 解析失败: {exc}") from exc
    return _normalize_scenario_collection(payload, path)
