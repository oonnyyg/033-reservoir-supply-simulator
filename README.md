# 水库逐日供水模拟工具

用本地逐日来水与需水记录，比较不同库容、最低保留水量与每日放水上限下的供水效果，
并给出可逐日核对的水量收支。仅使用 Python 标准库，无需安装第三方依赖，需要 Python 3.12+。

## 输入文件

### 情景 JSON（多个命名情景）

顶层可以是“名称 -> 情景参数”的映射（推荐），也可以是带 `name` 字段的对象列表，
或包一层 `{"scenarios": ...}`。每个情景包含：

| 字段 | 含义 | 约束 |
| --- | --- | --- |
| `total_capacity` | 总库容（立方米） | 必须为正数 |
| `initial_storage` | 初始蓄水（立方米） | 0 ≤ 值 ≤ 总库容 |
| `reserve` | 最低保留水量（立方米） | 0 ≤ 值 ≤ 总库容 |
| `max_release` | 每日放水上限（立方米） | 非负 |

所有数值必须为有限值，不得为负数；保留水量超过库容、初始水量越界都会整批拒绝。

### 逐日数据 CSV

必需列：`date, inflow, evaporation_demand, eco_demand, domestic_demand, irrigation_demand`

- `date` 为 `YYYY-MM-DD`，允许乱序（读取后排序），重复或缺失日期会指出具体日期与行号；
- 其余列为来水、蒸发需求、生态/生活/灌溉需水（立方米），必须为有限非负数。

## 每日计算顺序

1. **来水**：期初蓄水加上当天来水；
2. **蒸发**：扣实际蒸发，最多扣到蓄水为零（实际蒸发不超过蒸发需求）；
3. **供水**：只能使用超过最低保留水量的部分，按生态 → 生活 → 灌溉顺序逐项分配，
   各项不超过自身需求，且三类供水合计不超过每日放水上限；
4. **弃水**：分配后超过总库容的部分记为弃水，剩余蓄水为期末蓄水，进入次日。

逐日水量平衡恒等式：

```
期初蓄水 + 来水 = 实际蒸发 + 生态供水 + 生活供水 + 灌溉供水 + 弃水 + 期末蓄水
```

不足水量体现为缺水（供水 < 需求），不会被记成负蓄水。逐日 CSV 的 `balance_residual`
列给出当天平衡残差，可用于核对。

## 汇总口径

- 每个情景独立从其初始蓄水开始；按类别汇总总需求、总供水、总缺水与缺水天数；
- 缺水天数：当天该类供水小于需求即计 1 天；`any` 为任一类别缺水的天数；
- 满足率 = 总供水 / 总需求；总需求为零时满足率记为 1；
- 情景相互独立、顺序不影响结果，相同输入重复运行结果一致。

## 调用示例

```bash
python -m reservoir_sim \
  --scenarios examples/scenarios.json \
  --data examples/daily.csv \
  --out-dir out
```

也可在安装后使用控制台脚本：

```bash
pip install -e .
reservoir-sim --scenarios examples/scenarios.json --data examples/daily.csv --out-dir out
```

输出（`--out-dir` 不存在会自动创建）：

- `out/<情景名>_daily.csv`：各情景逐日记录，含期初期末蓄水、实际蒸发、
  各类供水与缺水、弃水及平衡残差；
- `out/summary.json`：各情景汇总（可用 `--summary` 改名）。

任一输入非法时，程序输出错误原因并以退出码 1 结束，不产生部分结果。

### 作为库调用

```python
from reservoir_sim import simulate
from reservoir_sim.io import read_daily_csv, read_scenarios_json
from reservoir_sim.report import build_summary

scenarios = read_scenarios_json("examples/scenarios.json")
days = read_daily_csv("examples/daily.csv")
for scenario in scenarios:
    records = simulate(scenario, days)
    print(scenario.name, build_summary(scenario, records)["satisfaction_rate"])
```

## 测试

```bash
python -m unittest discover -s tests -v
```
