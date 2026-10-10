# -*- coding: utf-8 -*-
"""建立小篆部件反查索引。"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Set

try:
    from .decompose import load_ids, parts_of
except ImportError:
    from decompose import load_ids, parts_of


def _parts_key(parts: List[str]) -> str:
    """将部件列表归一化为按 Unicode 码位排序、去重后的字符串键。

    :param parts: 部件列表（可能包含重复）
    :return: 排序去重后直接拼接的 key
    """
    seen: Set[str] = set()
    unique: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    # Python 字符串默认按 Unicode 码位排序
    return "".join(sorted(unique))


def build(ids_path: str, seal_chars: str, alias: Dict[str, str]) -> Dict[str, Any]:
    """建立反查索引并落盘 compose/index.json。

    只收录「有真篆形」且能拆出部件的字。
    每个字算出部件集合 key（部件按 Unicode 码位排序后拼接，去重）。

    :param ids_path: ids.txt 路径
    :param seal_chars: 有真篆形的字符集合字符串
    :param alias: 楷书偏旁 -> 正字 的映射
    :return: 索引字典
    """
    ids: Dict[str, str] = load_ids(ids_path)
    seal_set: Set[str] = set(seal_chars)

    by_parts: Dict[str, List[str]] = {}
    by_char: Dict[str, List[str]] = {}

    for char, _ids_seq in ids.items():
        if char not in seal_set:
            continue
        parts: List[str] = parts_of(char, ids, alias)
        if not parts:
            # 独体字或无法拆解，不收录到反查索引
            continue
        by_char[char] = list(parts)
        key = _parts_key(parts)
        by_parts.setdefault(key, []).append(char)

    # 对每个 key 下的字按 Unicode 码位排序，保证输出稳定
    for key in by_parts:
        by_parts[key].sort()

    index: Dict[str, Any] = {
        "version": 1,
        "by_parts": by_parts,
        "by_char": by_char,
        "stats": {
            "chars": len(by_char),
            "keys": len(by_parts),
        },
    }

    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return index


if __name__ == "__main__":
    # 本文件由 compose/cli.py --build 调用，不直接作为命令行工具。
    print("请通过 compose/cli.py --build 重建索引。", file=sys.stderr)
