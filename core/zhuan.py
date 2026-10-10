"""小篆转换的统一入口。

组合三块能力：

1. :class:`~core.seal_index.SealIndex` —— 现代汉字 ↔ Unicode 小篆码位
2. :class:`~core.pinyin_engine.PinyinEngine` —— 拼音 → 汉字候选
3. OpenCC ``TSCharacters.txt`` —— 简体 → 《说文》所用正字（多为繁体）

字形是否**真的打得出**，由 ``data/glyph_coverage.json``（``font/build_font.py``
的产物）把关：Unicode 的小篆区块有 11,328 个码位，而全字库说文解字只收了
6,738 个汉字，对不上的码位没有字形，必须过滤，否则上屏是豆腐块。

另有一层**补区**：Unicode 18.0 的小篆区块并未涵盖《说文》全部字（实测「七」
「二」「五」「小」「之」等常用字的 ``kSEAL_MCJK`` 被记成了扩展区古字，因而查
不到码位）。这类字改用补区 PUA-A 承载（``0xF0000 + (码位 - 0x3400)``）。

对外主接口::

    eng = ZhuanEngine()
    eng.candidates("shui")            # 拼音候选（含篆形）
    eng.char_to_seal("水")            # 单字转小篆
    eng.text_to_seal("流水")          # 整段转小篆（返回结果与缺字列表）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .pinyin_engine import Candidate, PinyinEngine
from .seal_index import SealIndex

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

#: 补区 PUA 起始与公式原点（见 tools/fetch_pua.py）
PUA_BASE = 0xF0000
PUA_ORIGIN = 0x3400


def _load_simp2trad(path: Path) -> dict[str, list[str]]:
    """读 OpenCC 的 TSCharacters.txt（繁->简）并反转成 简->繁。"""
    table: dict[str, list[str]] = {}
    if not path.is_file():
        return table
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            trad, simp_field = parts[0].strip(), parts[1].strip()
            if not trad or not simp_field:
                continue
            for simp in simp_field.split():
                table.setdefault(simp, []).append(trad)
    return table


@dataclass(frozen=True)
class SealResult:
    """转换结果。"""

    text: str  # 转换后的小篆串（缺字处保留原字）
    miss: tuple[str, ...]  # 没有篆形的原字

    @property
    def ok(self) -> bool:
        return not self.miss


class ZhuanEngine:
    """拼音/汉字 → 小篆。"""

    def __init__(self, root: str | Path | None = None, use_cache: bool = True) -> None:
        self.root = Path(root) if root else DEFAULT_ROOT
        self.index = SealIndex(self.root / "data" / "SealSources.txt")
        cache = self.root / "data" / "pinyin_cache.json" if use_cache else None
        self.pinyin = PinyinEngine(cache=cache)
        self._simp2trad = _load_simp2trad(self.root / "data" / "TSCharacters.txt")
        self._covered, self._pua = self._load_coverage(
            self.root / "data" / "glyph_coverage.json"
        )

    @staticmethod
    def _load_coverage(path: Path) -> tuple[set[str] | None, dict[str, int]]:
        """读字形覆盖表，返回（主区有字形的 Seal 码位, 补区 汉字->PUA码位）。

        ``None`` 表示没有覆盖表 —— 此时不限制主区（退回旧行为，
        便于在构建产物缺失时仍能跑转换内核）。
        """
        if not path.is_file():
            return None, {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, {}
        if not isinstance(raw, dict):
            return None, {}
        seal = set(raw.get("seal") or "")
        pua_raw = raw.get("pua") or {}
        pua = {k: int(v) for k, v in pua_raw.items() if isinstance(k, str)}
        return (seal or None), pua

    # ---- 单字 -----------------------------------------------------
    def _seal_ok(self, seal_char: str) -> bool:
        """该小篆码位在字体里是否真有字形。"""
        return self._covered is None or seal_char in self._covered

    def _lookup(self, char: str) -> str | None:
        """查篆形：Unicode 小篆区块 -> 简繁规范化重试 -> 补区。

        主区命中的码位还要过一道字形覆盖检查：Unicode 有码位、但字体里
        没有字形的，等于打不出来，得继续往补区找。
        """
        hit = self.index.seal_of(char)
        if hit and self._seal_ok(hit):
            return hit
        for trad in self._simp2trad.get(char, ()):
            hit = self.index.seal_of(trad)
            if hit and self._seal_ok(hit):
                return hit
        # 补区：Unicode 没有码位的《说文》字
        pua = self._pua.get(char)
        if pua:
            return chr(pua)
        for trad in self._simp2trad.get(char, ()):
            pua = self._pua.get(trad)
            if pua:
                return chr(pua)
        return None

    @staticmethod
    def is_pua(char: str) -> bool:
        """该字形是否来自补区（PUA）——补区字符离开本字体不可移植。"""
        cp = ord(char)
        return PUA_BASE <= cp <= PUA_BASE + (0x9FFF - PUA_ORIGIN)

    def char_to_seal(self, char: str) -> str | None:
        """单字转小篆；无篆形返回 None。"""
        if len(char) != 1:
            raise ValueError(f"char_to_seal 只接受单个字符，收到 {char!r}")
        return self._lookup(char)

    def has_seal(self, char: str) -> bool:
        return self._lookup(char) is not None

    # ---- 整段 -----------------------------------------------------
    def text_to_seal(self, text: str) -> SealResult:
        """整段转换；非汉字原样保留，缺篆形的字原样保留并记入 miss。"""
        out: list[str] = []
        miss: list[str] = []
        for ch in text:
            if not self._is_han(ch):
                out.append(ch)
                continue
            seal = self._lookup(ch)
            if seal:
                out.append(seal)
            else:
                out.append(ch)
                miss.append(ch)
        return SealResult(text="".join(out), miss=tuple(miss))

    # ---- 拼音 -----------------------------------------------------
    def candidates(self, pinyin: str, limit: int = 20, require_seal: bool = True) -> list[Candidate]:
        """拼音 → 候选字（默认只给有篆形的）。"""
        return self.pinyin.candidates(
            pinyin, seal_of=self._lookup, limit=limit, require_seal=require_seal
        )

    def pinyin_to_seal(self, pinyin: str) -> SealResult:
        """拼音直接转小篆（取第一个候选）。"""
        cands = self.candidates(pinyin, limit=1)
        if not cands:
            raise ValueError(f"没有匹配「{pinyin}」的篆字")
        c = cands[0]
        return SealResult(text=c.seal or c.hanzi, miss=() if c.seal else (c.hanzi,))

    # ---- 工具 -----------------------------------------------------
    @staticmethod
    def _is_han(ch: str) -> bool:
        cp = ord(ch)
        return (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2FA1F
        )

    @property
    def seal_count(self) -> int:
        return len(self.index)
