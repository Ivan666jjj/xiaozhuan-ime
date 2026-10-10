#!/usr/bin/env python3
"""把拼音 -> 小篆词典导出成 JSON，供输入法（Swift）直接读取。

输出结构::

    {
      "version": 1,
      "meta": {"sealCount": 11328, "puaCount": 1234},
      "dict": {
        "shui": [["水", "\u0003ef5e"], ["说", "\u0003d6db"]],
        ...
      }
    }

每个候选是 ``[汉字, 小篆字符]``；若有多个篆形（重文）取正篆。
只收录**有篆形**的字——输入法里打不出来的候选没有意义。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.zhuan import ZhuanEngine  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="导出拼音->小篆 词典")
    ap.add_argument("--out", default=str(ROOT / "ime" / "Resources" / "seal_dict.json"))
    ap.add_argument("--limit", type=int, default=30, help="每个拼音最多保留多少候选")
    args = ap.parse_args()

    eng = ZhuanEngine()
    index = eng.pinyin._index  # 拼音 -> [汉字]

    out: dict[str, list[list[str]]] = {}
    n_seal = n_pua = 0
    for py in index:
        # 直接用引擎的候选接口，保证与「转换内核」的排序完全一致
        cands = eng.candidates(py, limit=args.limit, require_seal=True)
        row: list[list[str]] = []
        for c in cands:
            assert c.seal is not None
            if ZhuanEngine.is_pua(c.seal):
                n_pua += 1
            else:
                n_seal += 1
            row.append([c.hanzi, c.seal])
        if row:
            out[py] = row

    payload = {
        "version": 1,
        "meta": {
            "sealCount": n_seal,
            "puaCount": n_pua,
            "pinyinCount": len(out),
        },
        "dict": out,
    }
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    size = dest.stat().st_size
    print(f"导出 {len(out)} 个拼音条目，主区候选 {n_seal}、补区候选 {n_pua}")
    print(f"-> {dest} ({size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
