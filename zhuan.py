#!/usr/bin/env python3
"""小篆命令行工具。

    python3 zhuan.py shui ren shan          # 每个拼音给出候选
    python3 zhuan.py --text "流水说小"       # 整段转小篆
    python3 zhuan.py --json shui            # 结构化输出
    python3 zhuan.py --strict --text "流水"  # 有缺字时非零退出
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.zhuan import ZhuanEngine  # noqa: E402


def show_codepoints(text: str) -> str:
    """把结果里的非 BMP / 篆字显示成可读的 U+ 形式，其余原样。"""
    out = []
    for ch in text:
        cp = ord(ch)
        if cp > 0xFFFF or 0x3D000 <= cp <= 0x3FC3F or 0xF0000 <= cp <= 0xFFFFD:
            out.append(f"U+{cp:04X}")
        else:
            out.append(ch)
    return " ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="拼音/汉字 -> 小篆")
    ap.add_argument("pinyin", nargs="*", help="一个或多个无声调拼音")
    ap.add_argument("--text", help="直接把一段中文转小篆")
    ap.add_argument("--limit", type=int, default=10, help="每个拼音显示多少候选")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--strict", action="store_true", help="有缺篆形的字时非零退出")
    ap.add_argument("--codepoints", action="store_true", help="显示码位而非字形")
    ap.add_argument("--root", help="工程根目录（默认自动定位）")
    args = ap.parse_args()

    eng = ZhuanEngine(root=args.root)
    result: dict[str, object] = {}
    miss_all: list[str] = []

    if args.text is not None:
        r = eng.text_to_seal(args.text)
        miss_all.extend(r.miss)
        result["text"] = {
            "input": args.text,
            "seal": r.text,
            "miss": list(r.miss),
        }
        if not args.json:
            print(r.text if not args.codepoints else show_codepoints(r.text))
            if r.miss:
                print(f"  （{len(r.miss)} 个字无篆形：{''.join(r.miss)}）", file=sys.stderr)

    for py in args.pinyin:
        cands = eng.candidates(py, limit=args.limit)
        entry = [
            {"hanzi": c.hanzi, "seal": c.seal, "codepoint": f"U+{ord(c.seal):04X}" if c.seal else None}
            for c in cands
        ]
        result.setdefault("pinyin", {})[py] = entry
        if not args.json:
            if not cands:
                print(f"{py}: （没有带篆形的候选）", file=sys.stderr)
                continue
            head = "  ".join(
                (show_codepoints(c.seal) if args.codepoints else c.seal) + f"({c.hanzi})"
                for c in cands[: args.limit]
            )
            print(f"{py}: {head}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and miss_all:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
