# 水库逐日供水模拟工具

使用本地来水与需水记录，比较不同**总库容、最低保留水量、每日放水上限**下的供水效果，
并逐日给出可核对的水量收支。仅依赖 Python 标准库（Python ≥ 3.12）。

## 输入文件

### 情景 JSON

顶层可以是列表，也可以是 `{"scenarios": [...]}`（见 `examples/scenarios.json`）。
每个情景的字段，单位均为立方米：

| 字段 | 含义 |
| --- | --- |
| `name` | 情景名称（不可为空、不可重复） |
| `total_capacity` | 总库容 |
| `initial_storage` | 初始蓄水（0 ≤ 值 ≤ 总库容） |
| `dead_storage` | 最低保留水量（不得超过总库容） |
| `daily_release_cap` | 每日放水上限 |

### 逐日 CSV

列：`date,inflow,evaporation,ecological_demand,domestic_demand,irrigation_demand`
（见 `examples/daily_inputs.csv`）。

- 日期格式 `YYYY-MM-DD`，允许乱序，读入后按日期升序排列；
- 日期必须按天连续；重复日期与缺失日期都会指出具体行号/缺口位置；
- 所有数值必须是有限数且非负；
- 任何非法输入都会**整批拒绝**，不产生部分结果。

## 每日计算顺序

1. 取期初蓄水 `storage_start`；
2. 加入来水 `inflow`；
3. 扣实际蒸发：`evaporation_actual = min(evaporation_demand, 蓄水)`，最多扣到蓄水为零；
4. 可放水量 = `max(0, 当前蓄水 - dead_storage)`；按**生态 → 生活 → 灌溉**顺序供水：
   - 单项供水不超过该项需求；
   - 三类供水合计不超过 `daily_release_cap`；
5. 仍超过 `total_capacity` 的部分记为弃水 `spill`；
6. 剩余蓄水 `storage_end` 进入次日。

水量收支恒等式（逐日 CSV 的 `balance_residual` 为其残差，应为 0）：

```
storage_start + inflow = evaporation + 三类供水合计 + spill + storage_end
```

蓄水永远不会出现负值；水量不足时表现为缺水而不是负蓄水。

## 命令行用法

安装脚本入口（可选）：

```powershell
pip install -e .
reservoir-sim --scenarios examples/scenarios.json --inputs examples/daily_inputs.csv --out-dir out
```

不安装直接运行：

```powershell
python -m reservoir_sim --scenarios examples/scenarios.json `
    --inputs examples/daily_inputs.csv --out-dir out
```

输出：

- `out/daily_<情景名>.csv`：每个情景的逐日记录，列包括
  期初期末蓄水、实际蒸发、三类供水与缺水、合计供水/缺水、弃水及收支残差；
- `out/summary.json`：各情景汇总（参数、总来水、总蒸发、总弃水、期末蓄水，
  按生态/生活/灌溉分类的总需求、总供水、总缺水、缺水天数，以及整体满足率）。

## 汇总口径

- **缺水**：某日某类供水小于需求即计为一个缺水天数；缺水量 = 需求 − 供水；
- **满足率**：`总供水 / 总需求`；总需求为零时满足率定义为 1；
- 各情景从各自的初始蓄水独立模拟，情景顺序不影响结果；
- 相同输入重复运行结果一致（无随机过程、无优化调度、无并行）。

## Python API

```python
from reservoir_sim.io import load_scenarios, load_daily_inputs
from reservoir_sim.simulate import run_scenario

scenarios = load_scenarios("examples/scenarios.json")
daily = load_daily_inputs("examples/daily_inputs.csv")
for scenario in scenarios:
    result = run_scenario(scenario, daily)
    print(result["summary"]["name"], result["summary"]["satisfaction_ratio"])
```

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

测试覆盖：正常供水与结转、连续枯水、满库弃水、蒸发耗尽、
需水优先级与放水上限、保留水量、零需求满足率、确定性，以及重复/缺失日期与非法数值等输入校验。
