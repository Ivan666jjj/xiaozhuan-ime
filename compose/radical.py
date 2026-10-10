import json
from typing import Any, Dict, List, Optional


def load(path: str) -> Dict[str, Any]:
    """加载 radical_index.json"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _seal_char_from_code(seal_code: Optional[str]) -> Optional[str]:
    """将 U+XXXX 格式的码位字符串转换为字符，失败返回 None"""
    if not seal_code:
        return None
    try:
        if seal_code.startswith('U+') or seal_code.startswith('u+'):
            return chr(int(seal_code[2:], 16))
        else:
            return chr(int(seal_code, 16))
    except (ValueError, TypeError):
        return None


def list_radicals(index: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """返回部列表：[{"index":1, "radical":"一", "seal_char":"…", "count":6}, …]
    seal_char 由 seal 码位字符串转换而来（"U+3D000" -> 对应字符）。
    limit=None 时返回全部 540 部。"""
    radicals = index.get('radicals', [])
    result = []
    for i, rad in enumerate(radicals):
        if limit is not None and i >= limit:
            break
        seal_char = _seal_char_from_code(rad.get('seal'))
        result.append({
            'index': rad.get('index'),
            'radical': rad.get('radical'),
            'seal_char': seal_char,
            'count': len(rad.get('members', []))
        })
    return result


def find_radical(radical_char: str, index: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """按部首汉字查找该部，返回 {"index":…, "radical":…, "seal_char":…, "members":[…]}。
    找不到返回 None。"""
    for rad in index.get('radicals', []):
        if rad.get('radical') == radical_char:
            seal_char = _seal_char_from_code(rad.get('seal'))
            return {
                'index': rad.get('index'),
                'radical': rad.get('radical'),
                'seal_char': seal_char,
                'members': rad.get('members', [])
            }
    return None


def members_of(radical_char: str, index: Dict[str, Any], char_to_seal: Optional[Dict[str, str]] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """返回该部的字（按《说文》顺序）：
    [{"char":"水", "seal_char":"…"}, …]
    char_to_seal 给了就填 seal_char（缺失时为 None），没给则 seal_char 一律 None。
    超过 limit 截断。"""
    rad = find_radical(radical_char, index)
    if rad is None:
        return []
    members = rad.get('members', [])
    result = []
    for i, char in enumerate(members):
        if i >= limit:
            break
        seal_char = None
        if char_to_seal is not None:
            seal_char = char_to_seal.get(char)
        result.append({
            'char': char,
            'seal_char': seal_char
        })
    return result
