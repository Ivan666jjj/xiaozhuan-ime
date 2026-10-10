#!/usr/bin/env python3
"""重建 compose/ 部件反查用的两个索引，与当前字形源保持一致。

``compose/cli.py`` 读这两个文件：

``data/char_to_seal.json``
    汉字 -> 小篆字符（只在**真的有字形**时才收录）
``data/seal_index.json``
    ``{"chars": 全部小篆字符, "count": N}``

字形源换成全字库之后，这两个文件必须用同一套覆盖表重建，
否则部件反查会给出字体里没有的篆形 —— 上屏就是豆腐块。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.pinyin_engine import CJK_RANGES  # noqa: E402
from core.zhuan import ZhuanEngine  # noqa: E402


def main() -> int:
    eng = ZhuanEngine()
    mapping: dict[str, str] = {}
    for lo, hi in CJK_RANGES:
        for cp in range(lo, hi + 1):
            seal = eng.char_to_seal(chr(cp))
            if seal:
                mapping[chr(cp)] = seal

    c2s = ROOT / "data" / "char_to_seal.json"
    c2s.write_text(
        json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    chars = sorted(set(mapping.values()))
    sidx = ROOT / "data" / "seal_index.json"
    sidx.write_text(
        json.dumps({"chars": "".join(chars), "count": len(chars)},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"汉字 -> 篆形 {len(mapping)} 条   -> {c2s} ({c2s.stat().st_size/1024:.0f} KB)")
    print(f"篆字去重 {len(chars)} 个        -> {sidx} ({sidx.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
