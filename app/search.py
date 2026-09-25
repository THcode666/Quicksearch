"""模糊搜索引擎。

匹配规则（全部不区分大小写、忽略多余空格）：
- 输入会被拆成多个关键词，要求**每个关键词**都能在
  「SOP名称 + 全部报警代码 + 解决方式」的组合文本中找到（AND 语义）。
- 因此输入 4303 能命中 E4303，输入 module not found 也能命中完整名称。
- 打分排序：完整命中某个报警代码 > 命中报警代码 > 命中名称 > 命中解决方式；
  同分时按修改时间新→旧排序。
纯内存计算，几千条 SOP 也是毫秒级，不读磁盘、不加载图片。
"""
from __future__ import annotations

from .store import Sop


def normalize(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def haystack(sop: Sop) -> str:
    return normalize(" ".join([sop.name, " ".join(sop.alarm_codes), sop.solution]))


def score(sop: Sop, query: str) -> int | None:
    """返回匹配得分；不匹配返回 None。"""
    q = normalize(query)
    if not q:
        return None
    tokens = q.split(" ")
    hay = haystack(sop)
    codes = normalize(" ".join(sop.alarm_codes))
    name = normalize(sop.name)
    total = 0
    for t in tokens:
        if t not in hay:
            return None
        if t in codes:
            total += 100
        elif t in name:
            total += 50
        else:
            total += 10
    if q in [normalize(c) for c in sop.alarm_codes]:
        total += 500  # 整个输入恰好是一个报警代码 → 置顶
    return total


def search(sops: list[Sop], query: str, limit: int = 50) -> list[tuple[Sop, int]]:
    """返回 [(sop, score)]，按得分降序、时间新→旧。"""
    results: list[tuple[Sop, int]] = []
    for s in sops:
        sc = score(s, query)
        if sc is not None:
            results.append((s, sc))

    def time_key(pair):
        return pair[0].updated_at or pair[0].created_at or ""

    results.sort(key=lambda p: (p[1], time_key(p)), reverse=True)
    return results[:limit]
