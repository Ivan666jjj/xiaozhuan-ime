# -*- coding: utf-8 -*-
"""小篆部件输入法查询模块。"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ALIAS_CACHE: Optional[Dict[str, str]] = None


def _load_alias() -> Dict[str, str]:
    """加载同目录下的 radical_alias.json，失败时返回空映射。"""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is not None:
        return _ALIAS_CACHE

    alias_path = Path(__file__).resolve().parent / "radical_alias.json"
    try:
        with alias_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _ALIAS_CACHE = {str(k): str(v) for k, v in data.items()}
        else:
            _ALIAS_CACHE = {}
    except Exception:
        _ALIAS_CACHE = {}
    return _ALIAS_CACHE


def _normalize_query(query_parts: List[str]) -> List[str]:
    """归一化查询部件：应用别名、丢弃空串、去重。"""
    alias = _load_alias()
    result: List[str] = []
    seen = set()

    for item in query_parts:
        if item is None:
            continue
        text = str(item)
        for ch in text:
            ch = ch.strip()
            if not ch:
                continue
            # 丢弃 IDS 结构符、方括号和纯 ASCII 字母
            if ch in "[]":
                continue
            if "\u2ff0" <= ch <= "\u2fff":
                continue
            if ch.isascii() and ch.isalpha():
                continue

            norm = alias.get(ch, ch)
            if norm not in seen:
                seen.add(norm)
                result.append(norm)

    return result


def load(path: str) -> Dict[str, Any]:
    """读 index.json。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def search(query_parts: List[str], index: Dict[str, Any], limit: int = 30) -> List[Dict[str, Any]]:
    """核心查询。

    规则：
    1. 把 query_parts 归一化(alias 映射、去重、按码位排序)得到 qkey。
    2. 精确匹配：index['by_parts'][qkey] 全部命中，排最前。
    3. 否则子集匹配：找出所有「部件集合 ⊇ qkey」的字，按 部件数从少到多 排序
       （部件越少说明匹配越紧凑），同数按码位。
    4. 返回 [{"char": 汉字, "parts": [...], "exact": True/False}]。
    """
    if limit <= 0:
        return []

    normalized = _normalize_query(query_parts)
    if not normalized:
        return []

    q_sorted = sorted(normalized, key=ord)
    qkey = "".join(q_sorted)
    qset = set(q_sorted)

    by_parts = index.get("by_parts", {})
    by_char = index.get("by_char", {})

    # 精确匹配
    exact_chars = by_parts.get(qkey)
    if exact_chars:
        result: List[Dict[str, Any]] = []
        for char in sorted(exact_chars, key=ord):
            parts = by_char.get(char)
            if not parts:
                parts = q_sorted
            result.append({"char": char, "parts": list(parts), "exact": True})
            if len(result) >= limit:
                break
        return result

    # 子集匹配
    candidates: List[Tuple[int, int, str, List[str]]] = []
    alias = _load_alias()
    for char, parts in by_char.items():
        if not parts:
            continue
        norm_parts = [alias.get(p, p) for p in parts]
        if qset.issubset(set(norm_parts)):
            candidates.append((len(parts), ord(char), char, parts))

    candidates.sort(key=lambda x: (x[0], x[1]))

    result = []
    for _, _, char, parts in candidates[:limit]:
        result.append({"char": char, "parts": list(parts), "exact": False})
    return result


def explain(char: str, index: Dict[str, Any]) -> str:
    """返回该字的部件编码显示，如 '沐 = 水 + 木'。没有则返回 '<char> (独体/未收录)'。"""
    by_char = index.get("by_char", {})
    parts = by_char.get(char)
    if parts:
        return f"{char} = {' + '.join(parts)}"
    return f"{char} (独体/未收录)"
