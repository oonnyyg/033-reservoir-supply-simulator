"""从 JSON 读取情景、从 CSV 读取逐日输入。"""

import csv
import datetime as dt
import json
import math

from .errors import InputValidationError
from .models import DEMAND_CATEGORIES, DailyInput, Scenario

CSV_COLUMNS = ("date", "inflow", "evaporation") + tuple(f"{c}_demand" for c in DEMAND_CATEGORIES)


def load_scenarios(path: str) -> list:
    """读取多个命名情景。

    支持顶层列表，或 ``{"scenarios": [...]}`` 对象。
    非法输入整批拒绝（不返回部分结果）。
    """
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise InputValidationError(f"情景 JSON 解析失败: {exc}") from exc

    if isinstance(data, dict) and "scenarios" in data:
        data = data["scenarios"]
    if not isinstance(data, list) or not data:
        raise InputValidationError("情景 JSON 必须包含非空的情景列表")

    scenarios = []
    problems = []
    seen_names = set()
    required = ("name", "total_capacity", "initial_storage", "dead_storage", "daily_release_cap")
    for index, item in enumerate(data):
        where = f"情景[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{where} 必须是对象")
            continue
        missing = [key for key in required if key not in item]
        if missing:
            problems.append(f"{where} 缺少字段: {', '.join(missing)}")
            continue
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{where} 的 name 必须是非空字符串")
        elif name in seen_names:
            problems.append(f"情景名称重复: {name!r}")
        else:
            seen_names.add(name)
        scenario = Scenario(
            name=name if isinstance(name, str) else f"<#{index}>",
            total_capacity=item["total_capacity"],
            initial_storage=item["initial_storage"],
            dead_storage=item["dead_storage"],
            daily_release_cap=item["daily_release_cap"],
        )
        try:
            scenario.validate()
        except InputValidationError as exc:
            problems.extend(exc.problems)
        else:
            scenarios.append(scenario)
    if problems:
        raise InputValidationError(problems)
    return scenarios


def _parse_float(value, where: str, problems: list) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        problems.append(f"{where} 不是数值: {value!r}")
        return math.nan
    if not math.isfinite(number):
        problems.append(f"{where} 必须是有限数值")
        return math.nan
    if number < 0:
        problems.append(f"{where} 不能为负数: {number}")
    return number


def load_daily_inputs(path: str) -> list:
    """读取逐日记录并完成全部校验。

    - 日期允许乱序，校验通过后按日期升序排列；
    - 重复日期指出其所在 CSV 数据行号；
    - 日期序列必须按天连续，缺失日期指出缺口位置；
    - 任何数值非法或日期非法时整批拒绝。
    """
    problems = []
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputValidationError("输入 CSV 为空或缺少表头")
        missing_columns = [col for col in CSV_COLUMNS if col not in reader.fieldnames]
        if missing_columns:
            raise InputValidationError(f"CSV 缺少列: {', '.join(missing_columns)}")
        for line_number, row in enumerate(reader, start=2):
            raw_date = (row.get("date") or "").strip()
            try:
                parsed_date = dt.date.fromisoformat(raw_date)
            except ValueError:
                problems.append(f"CSV 第 {line_number} 行日期非法: {raw_date!r}（应为 YYYY-MM-DD）")
                continue
            inflow = _parse_float(row.get("inflow"), f"CSV 第 {line_number} 行 inflow", problems)
            evaporation = _parse_float(row.get("evaporation"), f"CSV 第 {line_number} 行 evaporation", problems)
            demands = []
            for category in DEMAND_CATEGORIES:
                demands.append(
                    _parse_float(row.get(f"{category}_demand"), f"CSV 第 {line_number} 行 {category}_demand", problems)
                )
            rows.append((parsed_date, line_number, inflow, evaporation, tuple(demands)))

    if not rows:
        problems.append("CSV 没有任何数据行")
    if problems:
        raise InputValidationError(problems)

    seen = {}
    duplicates = []
    for parsed_date, line_number, *_ in rows:
        if parsed_date in seen:
            duplicates.append(
                f"日期 {parsed_date.isoformat()} 重复：第 {seen[parsed_date]} 行与第 {line_number} 行"
            )
        else:
            seen[parsed_date] = line_number
    if duplicates:
        raise InputValidationError(duplicates)

    rows.sort(key=lambda item: item[0])
    unique_dates = [item[0] for item in rows]
    missing = []
    for previous, current in zip(unique_dates, unique_dates[1:]):
        gap = (current - previous).days
        if gap > 1:
            missing_dates = [
                (previous + dt.timedelta(days=offset)).isoformat() for offset in range(1, gap)
            ]
            missing.append(
                f"{previous.isoformat()} 与 {current.isoformat()} 之间缺失 {gap - 1} 天: "
                + ", ".join(missing_dates)
            )
    if missing:
        raise InputValidationError(missing)

    return [
        DailyInput(date=parsed_date.isoformat(), inflow=inflow, evaporation=evaporation, demands=demands)
        for parsed_date, _line, inflow, evaporation, demands in rows
    ]
