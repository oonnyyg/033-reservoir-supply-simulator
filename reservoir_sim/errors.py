"""异常类型定义。"""


class SimulationError(Exception):
    """模拟过程中出现的错误基类。"""


class ValidationError(SimulationError):
    """输入数据校验失败（非法输入整批拒绝）。"""
