"""Unicode 18.0 小篆索引。

解析 UCD 的 SealSources.txt，建立「现代汉字 <-> 小篆字符」双向索引。

SealSources.txt 每行形如（制表符分隔）::

    U+3D000\tkSEAL_MCJK\t4E00

其中 kSEAL_MCJK 的值是该小篆字符对应的现代 CJK 汉字码位（十六进制）。
同一现代汉字可能有多个小篆形（重文），文件顺序中第一条视为正篆。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Unicode 18.0 小篆区块范围（U+3D000 - U+3FC3F，共 11,328 个码位）
SEAL_BLOCK = range(0x3D000, 0x3FC40)

_MCJK = "kSEAL_MCJK"
_RAD = "kSEAL_Rad"


class SealDataError(RuntimeError):
    """SealSources.txt 无法解析时抛出。"""


@dataclass(frozen=True)
class SealEntry:
    """一个小篆码位及其元数据。"""

    char: str  # 小篆字符（U+3D000 区块）
    modern: str  # 对应的现代汉字
    radical: str | None  # 所属部首的小篆字符
    sources: dict[str, str]  # THX/CCZ/QJZ/DYC 四个《说文》版本流水号

    @property
    def codepoint(self) -> int:
        return ord(self.char)


def parse(path: str | Path) -> list[SealEntry]:
    """解析 SealSources.txt，返回按文件顺序排列的条目列表。

    跳过空行与 ``#`` 开头的注释行；对每个小篆码位聚合它的各字段。
    无法解析的文件会抛 :class:`SealDataError`。
    """
    p = Path(path)
    if not p.is_file():
        raise SealDataError(f"找不到数据文件：{p}")

    # 先按小篆码位归组，保持首次出现顺序
    order: list[int] = []
    bucket: dict[int, dict[str, object]] = {}

    with p.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 3:
                # 真实数据中存在末尾多空列的个例，字段不足即视为坏行
                raise SealDataError(f"第 {lineno} 行字段不足 3 个：{line!r}")

            cp_field, key, value = fields[0].strip(), fields[1].strip(), fields[2].strip()
            if not cp_field.startswith("U+"):
                raise SealDataError(f"第 {lineno} 行码位格式非法：{cp_field!r}")
            try:
                cp = int(cp_field[2:], 16)
            except ValueError as exc:
                raise SealDataError(f"第 {lineno} 行码位无法解析：{cp_field!r}") from exc
            if cp not in SEAL_BLOCK:
                raise SealDataError(f"第 {lineno} 行不在小篆区块内：{cp_field}")

            if cp not in bucket:
                bucket[cp] = {"sources": {}}
                order.append(cp)
            rec = bucket[cp]

            if key == _MCJK:
                rec["modern"] = value
            elif key == _RAD:
                rec["radical"] = value
            elif key.startswith("kSEAL_"):
                rec["sources"][key[len("kSEAL_"):]] = value  # type: ignore[union-attr]

    entries: list[SealEntry] = []
    for cp in order:
        rec = bucket[cp]
        modern_cp = rec.get("modern")
        if not modern_cp:
            continue  # 个别篆形没有对应现代汉字，跳过
        try:
            modern = chr(int(str(modern_cp), 16))
        except ValueError as exc:
            raise SealDataError(f"U+{cp:04X} 的 kSEAL_MCJK 无法解析：{modern_cp!r}") from exc
        rad_cp = rec.get("radical")
        radical = None
        if rad_cp:
            # kSEAL_Rad 形如 "1.3D000"，取点号后的码位
            tail = str(rad_cp).split(".")[-1]
            try:
                radical = chr(int(tail, 16))
            except ValueError:
                radical = None
        entries.append(
            SealEntry(
                char=chr(cp),
                modern=modern,
                radical=radical,
                sources=dict(rec["sources"]),  # type: ignore[arg-type]
            )
        )
    if not entries:
        raise SealDataError(f"数据文件未解析出任何条目：{p}")
    return entries


def build_index(entries: list[SealEntry]) -> dict[str, list[str]]:
    """现代汉字 -> [小篆字符, ...]（顺序即正篆优先）。"""
    idx: dict[str, list[str]] = {}
    for e in entries:
        idx.setdefault(e.modern, []).append(e.char)
    return idx


def build_reverse(entries: list[SealEntry]) -> dict[str, SealEntry]:
    """小篆字符 -> 条目。"""
    return {e.char: e for e in entries}


class SealIndex:
    """加载一次、反复查询的小篆索引。"""

    def __init__(self, path: str | Path) -> None:
        self.entries = parse(path)
        self.modern_to_seal = build_index(self.entries)
        self.seal_to_entry = build_reverse(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def modern_count(self) -> int:
        """能查到小篆形的现代汉字个数。"""
        return len(self.modern_to_seal)

    def seal_of(self, char: str) -> str | None:
        """返回该现代汉字的正篆字符，没有则 None。"""
        forms = self.modern_to_seal.get(char)
        return forms[0] if forms else None

    def all_forms(self, char: str) -> list[str]:
        """返回该现代汉字的全部小篆形（重文）。"""
        return list(self.modern_to_seal.get(char, ()))

    def modern_of(self, seal_char: str) -> str | None:
        """由小篆字符反查现代汉字。"""
        e = self.seal_to_entry.get(seal_char)
        return e.modern if e else None
