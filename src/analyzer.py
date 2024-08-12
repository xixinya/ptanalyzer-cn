import os
import sys
from collections import defaultdict
from math import nan, isnan
from statistics import median
from time import sleep
from typing import Iterator, Callable, Optional, Union

from sty import rs, fg

from src.enums.damage_types import DT
from src.exceptions.bugged_run import BuggedRun
from src.exceptions.log_end import LogEnd
from src.exceptions.run_abort import RunAbort
from src.utils import color, time_str, oxfordcomma


class PTConstants:
    SHIELD_SWITCH = 'SwitchShieldVulnerability'  # 切换护盾
    SHIELD_PHASE_ENDINGS = {1: 'GiveItem Queuing resource load for Transmission: '
                               '/Lotus/Sounds/Dialog/FortunaOrbHeist/Business/DBntyFourInterPrTk0920TheBusiness',
                            3: 'GiveItem Queuing resource load for Transmission: '
                               '/Lotus/Sounds/Dialog/FortunaOrbHeist/Business/DBntyFourInterPrTk0890TheBusiness',
                            4: 'GiveItem Queuing resource load for Transmission: '
                               '/Lotus/Sounds/Dialog/FortunaOrbHeist/Business/DBntyFourSatelReal0930TheBusiness'}
    LEG_KILL = 'Leg freshly destroyed at part'  # 腿部刚被摧毁
    BODY_VULNERABLE = 'Camper->StartVulnerable() - The Camper can now be damaged!'  # 身体变得脆弱
    STATE_CHANGE = 'CamperHeistOrbFight.lua: Landscape - New State: '  # 状态改变
    PYLONS_LAUNCHED = 'Pylon launch complete'  # 支柱发射完成
    PHASE_1_START = 'Orb Fight - Starting first attack Orb phase'  # 第一阶段开始
    PHASE_ENDS = {1: 'Orb Fight - Starting second attack Orb phase',  # 第一阶段结束
                  2: 'Orb Fight - Starting third attack Orb phase',  # 第二阶段结束
                  3: 'Orb Fight - Starting final attack Orb phase',  # 第三阶段结束
                  4: ''}  # 第四阶段结束
    FINAL_PHASE = 4  # 最终阶段


class MiscConstants:
    NICKNAME = 'Net [Info]: name: '  # 昵称
    SQUAD_MEMBER = 'loadout loader finished.'  # 小队成员
    HEIST_START = 'jobId=/Lotus/Types/Gameplay/Venus/Jobs/Heists/HeistProfitTakerBountyFour'  # 抢劫开始
    HOST_MIGRATION = '"jobId" : "/Lotus/Types/Gameplay/Venus/Jobs/Heists/HeistProfitTakerBountyFour'  # 主机迁移
    HEIST_ABORT = 'SetReturnToLobbyLevelArgs: '  # 抢劫中止
    ELEVATOR_EXIT = 'EidolonMP.lua: EIDOLONMP: Avatar left the zone'  # 电梯出口
    BACK_TO_TOWN = 'EidolonMP.lua: EIDOLONMP: TryTownTransition'  # 返回城镇
    ABORT_MISSION = 'GameRulesImpl - changing state from SS_STARTED to SS_ENDING'  # 中止任务


class RelRun:

    def __init__(self,
                 run_nr: int,
                 nickname: str,
                 squad_members: set[str],
                 pt_found: float,
                 phase_durations: dict[int, float],
                 shield_phases: dict[float, list[tuple[DT, float]]],
                 legs: dict[int, list[float]],
                 body_dur: dict[int, float],
                 pylon_dur: dict[int, float]):
        self.run_nr = run_nr
        self.nickname = nickname
        self.squad_members = squad_members
        self.pt_found = pt_found
        self.phase_durations = phase_durations
        self.shield_phases = shield_phases
        self.legs = legs
        self.body_dur = body_dur
        self.pylon_dur = pylon_dur
        self.best_run = False
        self.best_run_yet = False

    def __str__(self):
        return '\n'.join((f'{key}: {val}' for key, val in vars(self).items()))

    @property
    def length(self):
        return self.phase_durations[4]

    @property
    def shield_sum(self) -> float:
        """所有阶段护盾时间的总和，不包括nan值。"""
        return sum(time for times in self.shield_phases.values() for _, time in times if not isnan(time))

    @property
    def leg_sum(self) -> float:
        """所有阶段腿部时间的总和。"""
        return sum(time for times in self.legs.values() for time in times)

    @property
    def body_sum(self) -> float:
        """所有阶段身体时间的总和。"""
        return sum(self.body_dur.values())

    @property
    def pylon_sum(self) -> float:
        """"所有阶段支柱时间的总和。"""
        return sum(self.pylon_dur.values())

    @property
    def sum_of_parts(self) -> float:
        """"战斗各部分时间的总和。这会切掉一些动画/等待时间。"""
        return self.shield_sum + self.leg_sum + self.body_sum + self.pylon_sum

    @property
    def shields(self) -> list[tuple[str, float]]:
        """不包含阶段的护盾，扁平化后的列表。"""
        return [shield_tuple for shield_phase in self.shield_phases.values() for shield_tuple in shield_phase]

    def pretty_print(self):
        print(color('-' * 72, fg.white))  # 标题

        self.pretty_print_run_summary()

        print(f'{fg.li_red}从电梯到利润收割者圆蛛花费了 {self.pt_found:.3f}s. '
              f'战斗持续时间: {time_str(self.length - self.pt_found, "units")}.\n')

        for i in [1, 2, 3, 4]:
            self.pretty_print_phase(i)

        self.pretty_print_sum_of_parts()

        print(f'{fg.white}{"-" * 72}\n\n')  # 尾部

    def pretty_print_run_summary(self):
        players = oxfordcomma([self.nickname] + list(self.squad_members - {self.nickname}))
        run_info = f'{fg.cyan}利润收割者圆蛛 第 {self.run_nr} 次由 {fg.li_cyan}{players}{fg.cyan} 以 ' \
                   f'{fg.li_cyan}{time_str(self.length, "units")} 清除'
        if self.best_run:
            run_info += f'{fg.white} - {fg.li_magenta}最佳运行!'
        elif self.best_run_yet:
            run_info += f'{fg.white} - {fg.li_magenta}迄今为止最佳运行!'
        print(f'{run_info}\n')

    def pretty_print_phase(self, phase: int):
        white_dash = f'{fg.white} - '
        print(f'{fg.li_green}> 阶段 {phase} {fg.li_cyan}{time_str(self.phase_durations[phase], "brackets")}')

        if phase in self.shield_phases:
            shield_sum = sum(time for _, time in self.shield_phases[phase] if not isnan(time))
            shield_str = f'{fg.white} | '.join((f'{fg.li_yellow}{s_type} {"?" if isnan(s_time) else f"{s_time:.3f}"}s'
                                                for s_type, s_time in self.shield_phases[phase]))
            print(f'{fg.white} 护盾切换:\t{fg.li_green}{shield_sum:7.3f}s{white_dash}{fg.li_yellow}{shield_str}')

        normal_legs = [f'{fg.li_yellow}{time:.3f}s' for time in self.legs[phase][:4]]
        leg_regen = [f'{fg.red}{time:.3f}s' for time in self.legs[phase][4:]]
        leg_str = f"{fg.white} | ".join(normal_legs + leg_regen)
        print(f'{fg.white} 腿部破坏:\t{fg.li_green}{sum(self.legs[phase]):7.3f}s{white_dash}{leg_str}')
        print(f'{fg.white} 身体击杀:\t{fg.li_green}{self.body_dur[phase]:7.3f}s')

        if phase in self.pylon_dur:
            print(f'{fg.white} 支柱:\t{fg.li_green}{self.pylon_dur[phase]:7.3f}s')

        if phase == 3 and self.shield_phases[3.5]:  # 打印阶段 3.5
            print(f'{fg.white} 额外护盾:\t\t   {fg.li_yellow}'
                  f'{" | ".join((str(shield) for shield, _ in self.shield_phases[3.5]))}')
        print('')  # 打印一个换行

    def pretty_print_sum_of_parts(self):
        print(f'{fg.li_green}> 各部分总和 {fg.li_cyan}{time_str(self.sum_of_parts, "brackets")}')
        print(f'{fg.white} 护盾切换:\t{fg.li_green}{self.shield_sum:7.3f}s')
        print(f'{fg.white} 腿部破坏:\t{fg.li_green}{self.leg_sum:7.3f}s')
        print(f'{fg.white} 身体击杀:\t{fg.li_green}{self.body_sum:7.3f}s')
        print(f'{fg.white} 支柱:\t{fg.li_green}{self.pylon_sum:7.3f}s')


class AbsRun:

    def __init__(self, run_nr: int):
        self.run_nr = run_nr
        self.nickname = ''
        self.squad_members: set[str] = set()
        self.heist_start = 0.0
        self.pt_found = 0.0
        self.shield_phases: dict[float, list[tuple[DT, float]]] = defaultdict(list)  # 阶段 -> 列表((类型, 绝对时间))
        self.shield_phase_endings: dict[int, float] = defaultdict(float)  # 阶段 -> 绝对时间
        self.legs: dict[int, list[float]] = defaultdict(list)  # 阶段 -> 列表(绝对时间)
        self.body_vuln: dict[int, float] = {}  # 阶段 -> 脆弱时间
        self.body_kill: dict[int, float] = {}  # 阶段 -> 击杀时间
        self.pylon_start: dict[int, float] = {}  # 阶段 -> 开始时间
        self.pylon_end: dict[int, float] = {}  # 阶段 -> 结束时间
        self.final_time: Optional[float] = None

    def __str__(self):
        return '\n'.join((f'{key}: {val}' for key, val in vars(self).items()))

    def post_process(self) -> None:
        """
        将一些时间信息重新排序，使其更加符合预期而不是实际得到的信息。
        如果最终护盾阶段没有记录护盾元素，抛出 `BuggedRun`。
        """
        # 从护盾阶段 3.5 取出最终护盾并前置到阶段 4。
        if len(self.shield_phases[3.5]) > 0:  # 如果玩家太快，不会有阶段 3.5 护盾。
            self.shield_phases[4] = [self.shield_phases[3.5].pop()] + self.shield_phases[4]

        # 从阶段 4 移除额外护盾。
        try:
            self.shield_phases[4].pop()
        except IndexError:
            raise BuggedRun(self, ['阶段 4 中未记录护盾。']) from None

    def check_run_integrity(self) -> None:
        """
        检查是否存在将运行转换为相对时间的所有必要信息。
        如果并非所有信息都存在，则该方法抛出BuggedRun和失败原因。
        """
        failure_reasons = []
        for phase in [1, 2, 3, 4]:
            # 护盾阶段（阶段 1、3、4）每阶段至少有 3 个护盾。
            # 默认是 5 个护盾，但由于伤害受护盾元素阶段的最大 HP 而不是剩余阶段的最大 HP 限制，
            # 每个护盾阶段至少可以达到 3 个元素
            if phase in [1, 3, 4] and len(self.shield_phases[phase]) < 3:
                failure_reasons.append(f'阶段 {phase} 记录了 {len(self.shield_phases[phase])} 个护盾元素，但至少预期有 3 个护盾元素。')

            # 每个阶段都有一个护甲阶段，每个护甲阶段至少需要摧毁 4 条腿
            # 如果记录的腿部摧毁少于 4 条，显然存在问题
            if len(self.legs[phase]) < 4:
                failure_reasons.append(f'阶段 {phase} 记录了 {len(self.legs[phase])} 条腿部，但至少预期有 4 条腿部。')

            # 计划摧毁 4 条腿。由于腿部重生错误，每个阶段最多可以摧毁 8 条腿
            # 如果某个阶段摧毁的腿部超过 8 条，则表示存在更严重的问题
            # 由于“更严重的问题”往往会损坏日志，因此我们会向用户发出警告
            # 该工具仍应能够转换并显示它，因此不会失败完整性检查
            if len(self.legs[phase]) > 8:
                print(color(f'阶段 {phase} 记录了 {len(self.legs[phase])} 条腿部击杀。\n'
                            f'如果你有此运行的录音并且战斗确实出现问题，请将问题报告给Warframe。\n'
                            f'如果你认为问题出在分析器上，请联系该工具的创建者。',
                            fg.li_red))

            # 必须存在护甲阶段中身体变得脆弱和被击杀的时间
            if phase not in self.body_vuln:
                failure_reasons.append(f'阶段 {phase} 中未记录利润收割者圆蛛的身体变得脆弱。')
            if phase not in self.body_kill:
                failure_reasons.append(f'阶段 {phase} 中未记录利润收割者圆蛛的身体被击杀。')

            # 如果在支柱阶段（阶段 1 和 3）未记录支柱开始时间或结束时间，则
            # 日志（可能还有战斗）出现问题。无法转换运行。
            if phase in [1, 3]:
                if phase not in self.pylon_start:
                    failure_reasons.append(f'阶段 {phase} 中未记录支柱阶段开始时间。')
                if phase not in self.pylon_end:
                    failure_reasons.append(f'阶段 {phase} 中未记录支柱阶段结束时间。')

        if failure_reasons:
            raise BuggedRun(self, failure_reasons)
        # 否则：隐式返回None

    def to_rel(self) -> RelRun:
        """
        将具有绝对时间的AbsRun转换为具有相对时间的RelRun。

        如果并非所有信息都存在，则抛出`BuggedRun`异常。
        """
        self.check_run_integrity()

        pt_found = self.pt_found - self.heist_start
        phase_durations = {}
        shield_phases = defaultdict(list)
        legs = defaultdict(list)
        body_dur = {}
        pylon_dur = {}

        previous_timestamp = self.pt_found
        for phase in [1, 2, 3, 4]:
            if phase in [1, 3, 4]:  # 具有护盾阶段的阶段
                # 注册护盾的时间和元素
                for i in range(len(self.shield_phases[phase]) - 1):
                    shield_type, _ = self.shield_phases[phase][i]
                    _, shield_end = self.shield_phases[phase][i + 1]
                    shield_phases[phase].append((shield_type, shield_end - previous_timestamp))
                    previous_timestamp = shield_end
                # 最后一个护盾的时间由护盾结束传输决定
                shield_phases[phase].append((self.shield_phases[phase][-1][0],
                                             self.shield_phase_endings[phase] - previous_timestamp))
                previous_timestamp = self.shield_phase_endings[phase]
            # 每个阶段都有一个护甲阶段
            for leg in self.legs[phase]:
                legs[phase].append(leg - previous_timestamp)
                previous_timestamp = leg
            body_dur[phase] = self.body_kill[phase] - self.body_vuln[phase]
            previous_timestamp = self.body_kill[phase]

            if phase in [1, 3]:  # 具有支柱阶段的阶段
                pylon_dur[phase] = self.pylon_end[phase] - self.pylon_start[phase]
                previous_timestamp = self.pylon_end[phase]

            # 设置阶段持续时间
            phase_durations[phase] = previous_timestamp - self.heist_start

        # 设置阶段 3.5 护盾（可能在非常快速的运行中没有）
        shield_phases[3.5] = [(shield, nan) for shield, _ in self.shield_phases[3.5]]

        return RelRun(self.run_nr, self.nickname, self.squad_members, pt_found,
                      phase_durations, shield_phases, legs, body_dur, pylon_dur)

    @property
    def failed_run_duration_str(self):
        if self.final_time is not None and self.heist_start is not None:
            return f'{fg.cyan}如果利润收割者圆蛛被击杀，运行可能持续了大约 ' \
                   f'{fg.li_cyan}{time_str(self.final_time - self.heist_start, "units")}.\n'
        return ''


class Analyzer:

    def __init__(self):
        self.follow_mode = False
        self.runs: list[Union[RelRun, RunAbort, BuggedRun]] = []
        self.proper_runs: list[RelRun] = []

    def run(self):
        filename = self.get_file()
        if self.follow_mode:
            self.follow_log(filename)
        else:
            self.analyze_log(filename)

    def get_file(self) -> str:
        try:
            self.follow_mode = False
            return sys.argv[1]
        except IndexError:
            print(fr"{fg.li_grey}正在以跟随模式打开 Warframe 的默认日志 %LOCALAPPDATA%/Warframe/EE.log。")
            print('跟随模式意味着运行将在你玩游戏时显示。 '
                  '利润收割者圆蛛 出现时也会打印第一个护盾。')
            print('请注意，你可以通过将文件拖到 exe 文件中来分析其他文件。')
            self.follow_mode = True
            try:
                return os.getenv('LOCALAPPDATA') + r'/Warframe/EE.log'
            except TypeError:
                print(f'{fg.li_red}你好 Linux 用户！请查阅 github.com/revoltage34/ptanalyzer 或 '
                      f'idalon.com/pt 上的README，以了解如何使跟随模式正常工作。')
                print(f'{rs.fg}按 ENTER 退出...')
                input()  # input(prompt) 不支持颜色编码，因此我们将其与打印分开。
                exit(-1)

    @staticmethod
    def follow(filename: str):
        """生成器函数，用于生成文件中的新行"""
        known_size = os.stat(filename).st_size
        with open(filename, 'r', encoding='latin-1') as file:
            # 开始无限循环
            cur_line = []  # 存储同一行的多个部分，以处理记录器提交不完整行的情况。
            while True:
                if (new_size := os.stat(filename).st_size) < known_size:
                    print(f'{fg.white}检测到重启。')
                    file.seek(0)  # 回到文件的开始
                    print('成功重新连接到 ee.log。现在监听新的 利润收割者圆蛛 运行。')
                known_size = new_size

                # 生成文件中的最后一行，并在延迟时跟随末尾
                while line := file.readline():
                    cur_line.append(line)  # 存储找到的内容。
                    if line[-1] == '\n':  # 遇到换行符，提交行
                        yield ''.join(cur_line)
                        cur_line = []
                # 文件中没有更多行 - 等待更多输入，然后再生成它。
                sleep(.1)

    def analyze_log(self, dropped_file: str):
        with open(dropped_file, 'r', encoding='latin-1') as it:
            try:
                require_heist_start = True
                while True:
                    try:
                        run = self.read_run(it, len(self.runs) + 1, require_heist_start).to_rel()
                        self.runs.append(run)
                        self.proper_runs.append(run)
                        require_heist_start = True
                    except RunAbort as abort:
                        self.runs.append(abort)
                        require_heist_start = abort.require_heist_start
                    except BuggedRun as buggedRun:
                        self.runs.append(buggedRun)
                        require_heist_start = True
            except LogEnd:
                pass

        # 确定最佳运行
        if len(self.proper_runs) > 0:
            best_run = min(self.proper_runs, key=lambda run_: run_.length)
            best_run.best_run = True

        # 显示所有运行
        if len(self.runs) > 0:
            for run in self.runs:
                if isinstance(run, RelRun):
                    run.pretty_print()
                else:  # 中止或出错的运行，只打印异常
                    print(run)

            if len(self.proper_runs) > 0:
                self.print_summary()
        else:
            print(f'{fg.white}未找到有效的 利润收割者圆蛛 运行。\n'
                  f'请注意，你必须在整个运行期间保持主机状态，以显示为有效运行。')

        print(f'{rs.fg}按 ENTER 退出...')
        input()  # input(prompt) 不支持颜色编码，因此我们将其与打印分开，并输入空字符串。

    def follow_log(self, filename: str):
        it = Analyzer.follow(filename)
        best_time = float('inf')
        require_heist_start = True
        while True:
            try:
                run = self.read_run(it, len(self.runs) + 1, require_heist_start).to_rel()
                self.runs.append(run)
                self.proper_runs.append(run)
                require_heist_start = True

                if run.length < best_time:
                    best_time = run.length
                    run.best_run_yet = True
                run.pretty_print()
                self.print_summary()
            except RunAbort as abort:
                print(abort)
                self.runs.append(abort)
                require_heist_start = abort.require_heist_start
            except BuggedRun as buggedRun:
                print(buggedRun)  # 打印运行失败的原因
                self.runs.append(buggedRun)
                require_heist_start = True

    def read_run(self, log: Iterator[str], run_nr: int, require_heist_start=False) -> AbsRun:
        """
        读取运行。
        :param log: ee.log 的迭代器，期望每次调用 next() 时返回一行。
        :param run_nr: 分配给此运行的编号（如果未中止）。
        :param require_heist_start: 指示此运行的开始是否表示前一次运行已中止。
        必要时正确初始化此运行。
        :raise RunAbort: 运行被中止，杀死序列出错，或在完成前重新启动。
        :raise BuggedRun: 运行已完成但缺少信息。
        :return: 战斗的绝对时间。
        """
        # 找到抢劫加载。
        if require_heist_start:  # 如果前一次中止表示新任务的开始，则不需要抢劫加载
            Analyzer.skip_until_one_of(log, [lambda line: MiscConstants.HEIST_START in line])

        run = AbsRun(run_nr)

        for phase in [1, 2, 3, 4]:
            self.register_phase(log, run, phase)  # 添加到运行的信息，包括开始时间
        run.post_process()  # 应用护盾阶段修正并检查运行完整性

        return run

    def register_phase(self, log: Iterator[str], run: AbsRun, phase: int) -> None:
        """
        根据日志中的信息为当前阶段注册 `self` 信息。
        """
        kill_sequence = 0
        while True:  # 匹配阶段 1-3，阶段 4 的杀死序列。
            pt_line_match = True
            try:
                line = next(log)
            except StopIteration:
                raise LogEnd()

            # 检查 PT 特定消息
            if PTConstants.SHIELD_SWITCH in line:  # 护盾切换
                # 护盾阶段 '3.5' 用于阶段 3 中支柱阶段期间护盾切换的情况。
                shield_phase = 3.5 if phase == 3 and 3 in run.pylon_start else phase
                run.shield_phases[shield_phase].append(Analyzer.shield_from_line(line))

                # 第一个护盾可以帮助确定是否中止。
                if self.follow_mode and len(run.shield_phases[1]) == 1:
                    print(f'{fg.white}第一个护盾: {fg.li_cyan}{run.shield_phases[phase][0][0]}')
            elif any(True for shield_end in PTConstants.SHIELD_PHASE_ENDINGS.values() if shield_end in line):
                run.shield_phase_endings[phase] = Analyzer.time_from_line(line)
            elif PTConstants.LEG_KILL in line:  # 腿部摧毁
                run.legs[phase].append(Analyzer.time_from_line(line))
            elif PTConstants.BODY_VULNERABLE in line:  # 身体脆弱 / 阶段 4 结束
                if kill_sequence == 0:  # 每个阶段只注册第一次无敌消息
                    run.body_vuln[phase] = Analyzer.time_from_line(line)
                kill_sequence += 1  # 一个阶段中有 3 次 BODY_VULNERABLE 意味着 PT 死亡。
                if kill_sequence == 3:  # PT 死亡。
                    run.body_kill[phase] = Analyzer.time_from_line(line)
                    return
            elif PTConstants.STATE_CHANGE in line:  # 通用状态变化
                # 在状态变化上进行通用匹配，以查找我们无法可靠找到的其他内容
                new_state = int(line.split()[8])
                # 状态 3、5 和 6 是阶段 1、2 和 3 的身体击杀。
                if new_state in [3, 5, 6]:
                    run.body_kill[phase] = Analyzer.time_from_line(line)
            elif PTConstants.PYLONS_LAUNCHED in line:  # 支柱发射完成
                run.pylon_start[phase] = Analyzer.time_from_line(line)
            elif PTConstants.PHASE_1_START in line:  # 利润收割者圆蛛 发现
                run.pt_found = Analyzer.time_from_line(line)
            elif PTConstants.PHASE_ENDS[phase] in line and phase != PTConstants.FINAL_PHASE:  # 阶段结束，除第 4 阶段外
                if phase in [1, 3]:  # 忽略阶段 2，因为它已匹配 body_kill。
                    run.pylon_end[phase] = Analyzer.time_from_line(line)
                return
            else:
                pt_line_match = False

            if pt_line_match:
                run.final_time = Analyzer.time_from_line(line)
                continue

            # 非 PT 特定消息
            if MiscConstants.NICKNAME in line:  # 昵称
                # 注意：由于Veilbreaker更新弄乱了名字，需要替换"î\x80\x80"
                run.nickname = line.replace(',', '').replace("î\x80\x80", "").split()[-2]
            elif MiscConstants.SQUAD_MEMBER in line:  # 小队成员
                # 注意：由于Veilbreaker更新弄乱了名字，需要替换"î\x80\x80"
                # 注意：字符可能代表玩家的平台
                run.squad_members.add(line.replace("î\x80\x80", "").split()[-4])
            elif MiscConstants.ELEVATOR_EXIT in line:  # 电梯出口（速度跑计时开始）
                if not run.heist_start:  # 仅使用第一次离开区域的时间，即抢劫开始。
                    run.heist_start = Analyzer.time_from_line(line)
            elif MiscConstants.HEIST_START in line:  # 找到新抢劫开始
                raise RunAbort(run, require_heist_start=False)
            elif MiscConstants.BACK_TO_TOWN in line or MiscConstants.ABORT_MISSION in line:
                raise RunAbort(run, require_heist_start=True)
            elif MiscConstants.HOST_MIGRATION in line:  # 主机迁移
                raise RunAbort(run, require_heist_start=True)

    @staticmethod
    def time_from_line(line: str) -> float:
        return float(line.split()[0])

    @staticmethod
    def shield_from_line(line: str) -> tuple[DT, float]:
        return DT.from_internal_name(line.split()[-1]), Analyzer.time_from_line(line)

    @staticmethod
    def skip_until_one_of(log: Iterator[str], conditions: list[Callable[[str], bool]]) -> tuple[str, int]:
        try:
            line = next(log)
            while not any((condition(line) for condition in conditions)):  # 跳过直到满足任一条件
                line = next(log)
            return line, next((i for i, cond in enumerate(conditions) if cond(line)))  # 返回第一个通过的索引
        except StopIteration:
            raise LogEnd()

    def print_summary(self):
        assert len(self.proper_runs) > 0
        best_run = min(self.proper_runs, key=lambda run: run.length)
        print(f'{fg.li_green}最佳运行:\t\t'
              f'{fg.li_cyan}{time_str(best_run.length, "units")} '
              f'{fg.cyan}(第 {best_run.run_nr} 次运行)')
        print(f'{fg.li_green}中间时间:\t\t'
              f'{fg.li_cyan}{time_str(median(run.length for run in self.proper_runs), "units")}')
        print(f'{fg.li_green}中间战斗持续时间:\t'
              f'{fg.li_cyan}{time_str(median(run.length - run.pt_found for run in self.proper_runs), "units")}\n')
        print(f'{fg.li_green}各部分中间数总和 {fg.li_cyan}'
              f'{time_str(median(run.sum_of_parts for run in self.proper_runs), "brackets")}')
        print(f'{fg.white} 中间护盾切换:\t{fg.li_green}'
              f'{median(run.shield_sum for run in self.proper_runs):7.3f}s')
        print(f'{fg.white} 中间腿部破坏:\t{fg.li_green}'
              f'{median(run.leg_sum for run in self.proper_runs):7.3f}s')
        print(f'{fg.white} 中间身体击杀:\t{fg.li_green}'
              f'{median(run.body_sum for run in self.proper_runs):7.3f}s')
        print(f'{fg.white} 中间支柱:\t\t{fg.li_green}'
              f'{median(run.pylon_sum for run in self.proper_runs):7.3f}s')

