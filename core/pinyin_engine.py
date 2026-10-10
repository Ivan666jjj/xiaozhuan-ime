"""拼音 -> 汉字候选。

用 pypinyin 给 CJK 基本区的字逐字注音，建立「无声调拼音 -> [汉字]」反查索引，
再按「有《说文》小篆字形优先、常用度次之」排序。

索引构建约需数秒，会被缓存到 ``data/pinyin_cache.json``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypinyin.pinyin_dict import pinyin_dict as _PINYIN_DICT

#: 参与注音的汉字区间（CJK 基本区 + 扩展 A）
CJK_RANGES: tuple[tuple[int, int], ...] = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))

#: 去声调：把带调拼音压成输入法实际敲入的字母（ü 记作 v）
_TONE_MAP = str.maketrans({
    "ā": "a", "á": "a", "ǎ": "a", "à": "a",
    "ē": "e", "é": "e", "ě": "e", "è": "e",
    "ī": "i", "í": "i", "ǐ": "i", "ì": "i",
    "ō": "o", "ó": "o", "ǒ": "o", "ò": "o",
    "ū": "u", "ú": "u", "ǔ": "u", "ù": "u",
    "ǖ": "v", "ǘ": "v", "ǚ": "v", "ǜ": "v", "ü": "v",
})


def strip_tone(pinyin: str) -> str:
    """带声调拼音 -> 纯字母（ü 统一成 v）。"""
    return pinyin.translate(_TONE_MAP).lower().strip()

#: 内置常用字序（前若干高频字，用于候选排序；缺省时退回码位序）
COMMON_HINT = (
    "的一是了我不人在他有这上们来到时大地为子中你说生国年着就那和要她出也得里后自以会"
    "家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总"
    "从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世"
    "什两次使身者被高已亲其进此话常与活正感水火山石土金木日月光明男女父母子女中大小上"
    "下左右东西南北春夏秋冬风雨雪云雷电江河湖海林森树草花叶果米麦牛羊马鸟鱼虫龙虎兔蛇"
    "王玉贝车舟门户心目耳手足口齿发身心血骨肉皮毛发丝线衣巾帽鞋袜"
)


@dataclass(frozen=True)
class Candidate:
    """一个拼音候选。"""

    hanzi: str  # 现代汉字
    seal: str | None  # 对应的小篆字符（无篆形则为 None）
    pinyin: str  # 规范化后的拼音

    @property
    def has_seal(self) -> bool:
        return self.seal is not None


def _iter_cjk() -> Iterable[str]:
    for lo, hi in CJK_RANGES:
        for cp in range(lo, hi + 1):
            yield chr(cp)


def _rank_table() -> dict[str, int]:
    """常用度名次表：优先用词频代理，退化时用手写的小常用字序。"""
    from .freq import char_frequency

    freq = char_frequency()
    if freq:
        return freq
    return {ch: i for i, ch in enumerate(COMMON_HINT)}


class PinyinEngine:
    """拼音反查引擎。"""

    def __init__(self, cache: str | Path | None = None) -> None:
        self._cache_path = Path(cache) if cache else None
        self._index: dict[str, list[str]] = {}
        self._rank = _rank_table()
        self._load_or_build()

    # ---- 索引构建 -------------------------------------------------
    def _load_or_build(self) -> None:
        if self._cache_path and self._cache_path.is_file():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self._index = {k: v for k, v in data.items()}
                return
            except (OSError, ValueError):
                pass
        self._index = self._build()
        if self._cache_path:
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                self._cache_path.write_text(
                    json.dumps(self._index, ensure_ascii=False), encoding="utf-8"
                )
            except OSError:
                pass

    def _build(self) -> dict[str, list[str]]:
        # 直接用 pypinyin 的单字字典：批量注音会把整串当成句子做词语消歧，
        # 导致「水」这类字拿不到 shui 的读音。
        index: dict[str, list[str]] = {}
        seen: dict[str, set[str]] = {}
        for cp, raw in _PINYIN_DICT.items():
            if not self._in_range(cp):
                continue
            ch = chr(cp)
            for py in str(raw).split(","):
                key = strip_tone(py)
                if not key.isalpha():
                    continue
                bucket = seen.setdefault(key, set())
                if ch in bucket:
                    continue  # 多音字可能把同一字映射到同一拼音，去重
                bucket.add(ch)
                index.setdefault(key, []).append(ch)
        return index

    @staticmethod
    def _in_range(cp: int) -> bool:
        return any(lo <= cp <= hi for lo, hi in CJK_RANGES)

    # ---- 查询 -----------------------------------------------------
    def _sort_key(self, ch: str) -> tuple[int, int]:
        r = self._rank.get(ch)
        return (0, r) if r is not None else (1, ord(ch))

    def candidates(
        self,
        pinyin: str,
        seal_of,
        limit: int = 20,
        require_seal: bool = False,
    ) -> list[Candidate]:
        """返回该拼音的候选列表。

        :param pinyin: 无声调拼音，如 ``"shui"``（大小写均可）
        :param seal_of: 可调用对象，``hanzi -> 小篆字符 | None``
        :param limit: 最多返回多少个
        :param require_seal: 只返回有篆形的字
        """
        key = pinyin.lower().strip()
        if not key.isalpha():
            return []
        pool = self._index.get(key, [])
        cands: list[Candidate] = []
        for ch in pool:
            seal = seal_of(ch)
            if require_seal and not seal:
                continue
            cands.append(Candidate(hanzi=ch, seal=seal, pinyin=key))
        # 有篆形的排前，再按常用度
        cands.sort(key=lambda c: (not c.has_seal, *self._sort_key(c.hanzi)))
        return cands[:limit]

    def known_pinyin(self, key: str) -> bool:
        return key.lower().strip() in self._index
