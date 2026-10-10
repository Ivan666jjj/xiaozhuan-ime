"""汉字常用度排序。

手边没有现成的字频表，这里用 pypinyin 的词组词典做代理：

* 一个字出现在越多的词组里，越常用（记一次）；
* 词越短权重越高（双字词的字比四字成语的字更常用）。

结果是一个 ``汉字 -> 名次`` 的字典，名次越小越常用。用于拼音候选的排序，
避免「水」被「䬽」「娷」这类生僻字挤到后面。
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache


@lru_cache(maxsize=1)
def char_frequency() -> dict[str, int]:
    """返回 汉字 -> 名次（0 最常用）。"""
    from pypinyin.phrases_dict import phrases_dict

    score: Counter[str] = Counter()
    for phrase in phrases_dict:
        weight = 1.0 / max(len(phrase), 1) * 100  # 短词权重高
        for ch in phrase:
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                score[ch] += weight

    # 按分数降序 -> 名次
    ordered = sorted(score.items(), key=lambda kv: (-kv[1], ord(kv[0])))
    return {ch: i for i, (ch, _) in enumerate(ordered)}


@lru_cache(maxsize=1)
def pinyin_frequency() -> dict[str, int]:
    """返回 拼音 -> 该拼音下所有字的最高常用度（越小越常用）。

    用于判定「这个拼音是不是常用拼音」，辅助整句切分。
    """
    from pypinyin.phrases_dict import phrases_dict
    from pypinyin.pinyin_dict import pinyin_dict

    from .pinyin_engine import strip_tone

    rank = char_frequency()
    best: dict[str, int] = {}
    for cp, raw in pinyin_dict.items():
        ch = chr(cp)
        r = rank.get(ch)
        if r is None:
            continue
        for py in str(raw).split(","):
            key = strip_tone(py)
            if key and (key not in best or r < best[key]):
                best[key] = r
    return best
