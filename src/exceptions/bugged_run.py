from __future__ import annotations

from typing import TYPE_CHECKING

from sty import fg

from src.utils import time_str

if TYPE_CHECKING:
    from src.analyzer import AbsRun


class BuggedRun(RuntimeError):
    """表示运行出现问题的异常——它没有足够的信息转换为相对运行。

    如果 require_heist_start 被设置为 True，分析器应该寻找 'job start' 行。
    否则，分析器可以假设新运行开始并中止了旧运行。"""
    def __init__(self, run: AbsRun, reasons: list[str]):
        self.run = run
        self.reasons = reasons

    def __str__(self):
        reason_str = '\n'.join(self.reasons)
        return f'{fg.li_red}利润收割者圆蛛 运行 #{self.run.run_nr} 出现问题，无法显示统计数据。 ' \
               f'发现的问题：\n{reason_str}\n' \
               f'{self.run.failed_run_duration_str}'
