"""输入数据校验错误。"""


class InputValidationError(ValueError):
    """非法输入：整批拒绝，错误信息中给出具体位置。"""

    def __init__(self, problems):
        if isinstance(problems, str):
            problems = [problems]
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))
