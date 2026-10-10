"""小篆部件输入法命令行接口。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Set, Tuple

try:
    from . import build_index
    from . import lookup
except ImportError:
    import build_index  # type: ignore
    import lookup  # type: ignore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS_PATH = os.path.join(BASE_DIR, "compose", "ids.txt")
SEAL_PATH = os.path.join(BASE_DIR, "data", "seal_index.json")
ALIAS_PATH = os.path.join(BASE_DIR, "compose", "radical_alias.json")
INDEX_PATH = os.path.join(BASE_DIR, "compose", "index.json")
CHAR_TO_SEAL_PATH = os.path.join(BASE_DIR, "data", "char_to_seal.json")


def load_alias(path: str = ALIAS_PATH) -> Dict[str, str]:
    """加载楷书偏旁到正字的映射。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：找不到别名文件 {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：别名文件 {path} 格式错误：{e}", file=sys.stderr)
        sys.exit(1)


def load_char_to_seal(path: str = CHAR_TO_SEAL_PATH) -> Dict[str, str]:
    """加载汉字到小篆字符的映射。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误：找不到小篆映射文件 {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：小篆映射文件 {path} 格式错误：{e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"错误：小篆映射文件 {path} 的格式必须是对象", file=sys.stderr)
        sys.exit(1)
    return data


def load_seal_data(path: str = SEAL_PATH) -> Tuple[Dict[str, str], Set[str]]:
    """加载篆形数据。

    返回 (char -> 篆形字符 的映射, 有篆形的字符集合)。
    如果 seal_index.json 中有 "glyphs" 字段，则使用它作为映射；
    否则认为字符本身即为篆形字符。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误：找不到篆形数据 {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：篆形数据 {path} 格式错误：{e}", file=sys.stderr)
        sys.exit(1)

    chars = data.get("chars", "")
    if not isinstance(chars, str):
        print(f"错误：篆形数据 {path} 的 chars 字段必须是字符串", file=sys.stderr)
        sys.exit(1)

    seal_set = set(chars)
    glyphs = data.get("glyphs", {})
    if not isinstance(glyphs, dict):
        glyphs = {}

    seal_map: Dict[str, str] = {}
    for ch in chars:
        seal_map[ch] = glyphs.get(ch, ch)
    return seal_map, seal_set


def cmd_build() -> int:
    """执行 --build：重建索引。"""
    seal_map, _ = load_seal_data()
    seal_chars = "".join(seal_map.keys())
    alias = load_alias()

    if not os.path.exists(IDS_PATH):
        print(f"错误：找不到 IDS 文件 {IDS_PATH}", file=sys.stderr)
        return 1

    try:
        index = build_index.build(IDS_PATH, seal_chars, alias)
    except Exception as e:
        print(f"错误：建立索引失败：{e}", file=sys.stderr)
        return 1

    try:
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"错误：无法写入索引文件 {INDEX_PATH}：{e}", file=sys.stderr)
        return 1

    print(f"索引已重建：{INDEX_PATH}", file=sys.stderr)
    return 0


def cmd_explain(char: str) -> int:
    """执行 --explain：显示某字的部件。"""
    if not os.path.exists(INDEX_PATH):
        print(f"错误：索引文件 {INDEX_PATH} 不存在，请先运行 --build 重建索引。", file=sys.stderr)
        return 1
    try:
        index = lookup.load(INDEX_PATH)
    except Exception as e:
        print(f"错误：加载索引失败：{e}", file=sys.stderr)
        return 1

    result = lookup.explain(char, index)
    print(result)
    return 0


def cmd_query(query_parts: List[str], use_json: bool) -> int:
    """执行查询：根据部件序列查找小篆字。"""
    if not os.path.exists(INDEX_PATH):
        print(f"错误：索引文件 {INDEX_PATH} 不存在，请先运行 --build 重建索引。", file=sys.stderr)
        return 1
    try:
        index = lookup.load(INDEX_PATH)
    except Exception as e:
        print(f"错误：加载索引失败：{e}", file=sys.stderr)
        return 1

    char_to_seal = load_char_to_seal()

    try:
        results = lookup.search(query_parts, index, limit=30)
    except Exception as e:
        print(f"错误：查询失败：{e}", file=sys.stderr)
        return 1

    if not results:
        print("未找到匹配的字。", file=sys.stderr)
        sys.exit(1)

    if use_json:
        out = []
        for item in results:
            char = item["char"]
            parts = item.get("parts", [])
            exact = item.get("exact", False)
            seal_char = char_to_seal.get(char)
            out.append({
                "char": char,
                "seal_char": seal_char,
                "parts": parts,
                "exact": exact,
            })
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for item in results:
            char = item["char"]
            parts = item.get("parts", [])
            seal_char = char_to_seal.get(char)
            if seal_char is None:
                seal_char = char
            parts_str = "+".join(parts) if parts else "独体"
            print(f"{seal_char}  {char}  ({parts_str})")

    return 0


def _load_radical_index() -> dict:
    """加载《说文》540 部索引（compose/radical_index.json）。"""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "radical_index.json")
    if not os.path.isfile(path):
        print(f"错误：找不到 {path}", file=sys.stderr)
        sys.exit(1)
    import radical as _r
    return _r.load(path)


def cmd_radicals() -> int:
    """列出全部 540 部的部序与部首。"""
    import radical as _r
    idx = _load_radical_index()
    rads = _r.list_radicals(idx)
    for i in range(0, len(rads), 8):
        row = rads[i:i + 8]
        print("  ".join(
            f"{r['index']:>3}.{r['radical'] or '□'}" for r in row))
    print(f"\n共 {len(rads)} 部（《说文解字》540 部）")
    return 0


def cmd_radical(name: str, as_json: bool) -> int:
    """列出某部的字（按《说文》顺序）。"""
    import radical as _r
    idx = _load_radical_index()
    base = os.path.dirname(os.path.abspath(__file__))
    c2s_path = os.path.join(base, os.pardir, "data", "char_to_seal.json")
    c2s = None
    if os.path.isfile(c2s_path):
        with open(c2s_path, encoding="utf-8") as fh:
            c2s = json.load(fh)

    rad = _r.find_radical(name, idx)
    if rad is None:
        print(f"错误：未找到部首「{name}」。可用 --radicals 查看全部 540 部。", file=sys.stderr)
        return 1
    members = _r.members_of(name, idx, char_to_seal=c2s, limit=10000)

    if as_json:
        print(json.dumps({
            "index": rad["index"], "radical": rad["radical"],
            "seal_char": rad["seal_char"],
            "count": len(members),
            "members": members,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"《说文》第 {rad['index']} 部 · {name}部")
    for i in range(0, len(members), 20):
        row = members[i:i + 20]
        print("  ".join(
            (m["seal_char"] or m["char"]) for m in row))
    print(f"\n（第{rad['index']}部，共{len(members)}字）")
    return 0


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="小篆部件输入法：输入部件序列反查小篆字。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 compose/cli.py 水工            # 查询
  python3 compose/cli.py --build         # 重建索引
  python3 compose/cli.py --explain 沐    # 显示某字的部件
  python3 compose/cli.py --json 水木     # JSON 输出
""",
    )
    parser.add_argument("--build", action="store_true", help="重建索引")
    parser.add_argument("--explain", metavar="CHAR", help="显示某字的部件")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出查询结果")
    parser.add_argument("--radical", metavar="CHAR", help="列出某部的字，如 --radical 水")
    parser.add_argument("--radicals", action="store_true", help="列出全部 540 部的部序与部首")
    parser.add_argument("query", nargs="*", help="查询部件序列，如 水工")

    args = parser.parse_args()

    if args.build:
        return cmd_build()

    if args.radicals:
        return cmd_radicals()

    if args.radical:
        return cmd_radical(args.radical, args.json)

    if args.explain:
        return cmd_explain(args.explain)

    if not args.query:
        print("错误：未指定操作或查询参数。请使用 --build、--explain 或提供查询部件序列。", file=sys.stderr)
        sys.exit(2)

    query_str = "".join(args.query)
    query_parts = list(query_str)
    return cmd_query(query_parts, args.json)


if __name__ == "__main__":
    sys.exit(main())
