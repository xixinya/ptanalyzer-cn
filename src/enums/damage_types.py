from __future__ import annotations
from typing import Optional

from src.enums.abbreviation_enum import AbbreviationEnum


class DT(AbbreviationEnum):
    IMPACT = '冲击', 'DT_IMPACT'
    PUNCTURE = '穿刺', 'DT_PUNCTURE'
    SLASH = '切割', 'DT_SLASH'

    COLD = '冰', 'DT_FREEZE'
    HEAT = '火', 'DT_FIRE'
    TOXIN = '毒', 'DT_POISON'
    ELECTRICITY = '电', 'DT_ELECTRICITY'

    GAS = '毒气', 'DT_GAS'
    VIRAL = '病毒', 'DT_VIRAL'
    MAGNETIC = '磁力', 'DT_MAGNETIC'
    RADIATION = '辐射', 'DT_RADIATION'
    CORROSIVE = '腐蚀', 'DT_CORROSIVE'
    BLAST = '爆炸', 'DT_EXPLOSION'

    @property
    def internal_name(self) -> str:
        """返回在Digital Extremes内部使用的名称。"""
        return self.values[1]

    @staticmethod
    def from_internal_name(name: str) -> Optional[DT]:
        """
        将给定的 ``name``（区分大小写）映射到对应的枚举。\n
        :param name: 匹配的内部名称。
        :return: 如果存在，与名称对应的枚举，否则返回默认值 None。
        """
        return next((enum_instance for enum_instance in iter(DT) if name == enum_instance.internal_name),
                    None)
