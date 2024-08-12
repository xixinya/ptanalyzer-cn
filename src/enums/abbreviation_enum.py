from __future__ import annotations

from typing import TypeVar, Type, Optional
from aenum import MultiValueEnum

_T = TypeVar('_T')


class AbbreviationEnum(MultiValueEnum):
    """
    为 ``MultiValueEnum`` 添加了一个 ``from_str`` 方法，允许将任何字符串多值映射到相应的
    枚举（不区分大小写）。

    重写了字符串 Dunder 方法，以显示值而不是枚举。
    """

    def __str__(self):
        return str(self.value)

    @classmethod
    def from_str(cls: Type[_T], name: str, default: _T = None) -> Optional[_T]:
        """
        将给定的 ``name``（不区分大小写）映射到 ``cls`` 的相应枚举类型。\n
        :param name: 需要匹配的字符串。
        :param default: 如果没有匹配的枚举，则返回的默认值。
        :return: 如果存在，与名称对应的枚举，否则返回默认值。
        """
        name = name.casefold()
        for enum_instance in iter(cls):
            for abbreviation in enum_instance.values:
                if name == abbreviation.casefold():
                    return enum_instance
        return default

    @classmethod
    def regex_match_any(cls) -> str:
        """
        返回一个正则表达式，用于匹配 ``cls`` 识别的任何值。\n
        :return: 由 ``cls`` 中的所有缩写组成的字符串，使用管道 | 分隔符。
        """
        return "|".join((abbr for enum in iter(cls) for abbr in enum.values))
