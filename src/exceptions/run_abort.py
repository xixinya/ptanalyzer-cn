from __future__ import annotations

from typing import TYPE_CHECKING

from sty import fg

from src.utils import time_str

if TYPE_CHECKING:
    from src.analyzer import AbsRun


class RunAbort(Exception):
    """表示运行已经中止的异常。

    如果 require_heist_start 被设置为 True，分析器应该寻找 'job start' 行。
    否则，分析器可以假设新运行开始并中止了旧运行。"""
    def __init__(self, run: AbsRun, *, require_heist_start: bool):
        self.run = run
        self.require_heist_start = require_heist_start

    def __str__(self):
        return f'{fg.cyan}利润收割者圆蛛 运行 #{self.run.run_nr} 已经中止或日志出现问题。\n' \
               f'{self.run.failed_run_duration_str}'
