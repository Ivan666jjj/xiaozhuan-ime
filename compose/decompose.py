import json
import os
import sys
from typing import Dict, List, Optional

_ALIAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "radical_alias.json")
_ALIAS_CACHE: Optional[Dict[str, str]] = None

# 单笔符号（不在 CJK 部首补充 U+2E80–U+2EFF 内）
_STROKE_CHARS = frozenset("一丨丶丿乙亅乀乁乚乛")

_CJK_IDEOGRAPH_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0x20000, 0x2FA1F),
)


def _is_stroke_char(ch: str) -> bool:
    code = ord(ch)
    if 0x31C0 <= code <= 0x31EF:
        return True
    if 0x2E80 <= code <= 0x2EFF:
        return False
    if 0x2F00 <= code <= 0x2F05:
        return True
    return ch in _STROKE_CHARS


def _is_cjk_ideograph(ch: str) -> bool:
    code = ord(ch)
    for lo, hi in _CJK_IDEOGRAPH_RANGES:
        if lo <= code <= hi:
            return True
    return False


def load_alias(path: Optional[str] = None) -> Dict[str, str]:
    """加载楷书偏旁到正字的映射表。

    参数:
        path: 映射表 JSON 文件路径，缺省使用 compose/radical_alias.json。

    返回:
        {偏旁: 正字} 字典；文件不存在或格式错误时返回空字典。
    """
    global _ALIAS_CACHE
    if path is None and _ALIAS_CACHE is not None:
        return _ALIAS_CACHE

    alias_path = path if path is not None else _ALIAS_PATH
    if not os.path.exists(alias_path):
        if path is None:
            _ALIAS_CACHE = {}
        return {}

    try:
        with open(alias_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print("警告: 读取偏旁映射失败 %s: %s" % (alias_path, exc), file=sys.stderr)
        if path is None:
            _ALIAS_CACHE = {}
        return {}

    if not isinstance(data, dict):
        print("警告: 偏旁映射格式不是字典: %s" % alias_path, file=sys.stderr)
        if path is None:
            _ALIAS_CACHE = {}
        return {}

    result: Dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            result[k] = v

    if path is None:
        _ALIAS_CACHE = result
    return result


def load_ids(path: str) -> Dict[str, str]:
    """读取 ids.txt，返回 {汉字: IDS序列}。

    跳过注释行（以 # 开头）和空行。
    每行按制表符分隔，取第 2 列为汉字、第 3 列为 IDS 序列。
    """
    result: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                continue

            cols = line.split("\t")
            if len(cols) < 3:
                print(
                    "警告: %s:%d 列数不足，已跳过: %s" % (path, lineno, line),
                    file=sys.stderr,
                )
                continue

            char = cols[1].strip()
            ids_seq = cols[2].strip()
            if not char:
                continue
            result[char] = ids_seq

    return result


def flatten(seq: str, alias: Optional[Dict[str, str]] = None) -> List[str]:
    """把 IDS 序列展平成部件列表。

    - 丢弃结构符 U+2FF0-U+2FFF
    - 丢弃 '[' ']'
    - 丢弃纯 ASCII 字母及其他 ASCII 字符
    - 非 ASCII 部件按 alias 表归一到正字
    - 去重并保持首次出现顺序
    - 若序列含笔画类字符、展平后含非汉字、或最终部件数 > 8，返回 []
    """
    if alias is None:
        alias = load_alias()

    # 检查 IDS 序列中是否含笔画类字符
    for ch in seq:
        if _is_stroke_char(ch):
            return []

    parts: List[str] = []
    seen = set()

    for ch in seq:
        code = ord(ch)

        # 丢弃 IDS 结构符
        if 0x2FF0 <= code <= 0x2FFF:
            continue

        # 丢弃 ASCII 字符：方括号、大写字母 G/T/K/V 等
        if ch.isascii():
            continue

        # 丢弃空白
        if ch.isspace():
            continue

        # 偏旁归一到正字
        normalized = alias.get(ch, ch)

        # 展平后得到的部件里不能含非汉字字符
        if not _is_cjk_ideograph(normalized):
            return []

        if normalized not in seen:
            seen.add(normalized)
            parts.append(normalized)

    if len(parts) > 8:
        return []

    return parts


def parts_of(char: str, ids: Dict[str, str], alias: Dict[str, str]) -> List[str]:
    """返回该字的部件列表。

    - 字不在 ids 里，返回 []
    - IDS 就是字本身（独体字），返回 []
    - 展平后部件数只有 1 个且该部件就是字本身，返回 []
    - 否则返回展平、去重后的部件列表
    """
    if char not in ids:
        return []

    seq = ids[char].strip()

    # 独体字：IDS 就是字本身
    if seq == char:
        return []

    parts = flatten(seq, alias)

    if len(parts) == 1 and parts[0] == char:
        return []

    return parts
