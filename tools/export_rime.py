#!/usr/bin/env python3
"""把输入法词典导出成 Rime 方案（Windows 小狼毫 / 安卓同文输入法可用）。

思路跟 macOS 版一致：**上屏的是普通汉字**，靠候选窗的字体把它渲染成篆形。
这样对方没装字体时看到的是楷体汉字，照样读得懂 —— 能分享、不掉豆腐块。

    python3 tools/export_rime.py

产物在 packaging/rime/ 下：
    shuowen.dict.yaml     词典（拼音 -> 汉字，按常用度排权重）
    shuowen.schema.yaml   输入方案
    default.custom.yaml   挂载方案 + 指定候选窗字体
    README.md             两个平台的安装说明
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Rime 词典的权重上限。我们的数据是「按常用度排序的单字表」，
#: 没有真实词频，所以按顺序递减赋权 —— 排在前面的候选权重高，
#: Rime 就会把它排前面，效果跟 macOS 版一致。
WEIGHT_TOP = 100


def normalize_pinyin(p: str) -> str:
    """把拼音规范成 Rime 键盘打得出的形式。

    Rime 的 speller 只认 a-z，而词表里有几个带声调符号的音节
    （`ń`、`ńg`、`ế`、`ề`，都是「哽」「欸」这类字）。这里去掉组合符号：
    `ń`->`n`、`ế`->`e`。返回空串表示这条没法用键盘输入。
    """
    s = unicodedata.normalize("NFD", p)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if "a" <= c <= "z")


def load_dict(path: Path) -> dict[str, list[str]]:
    """读 seal_dict.json，返回 {拼音: [汉字, ...]}（保持原顺序）。

    音节先做规范化，撞在一起的合并（如 `ế`/`ề` 都归到 `e`）。
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    table = raw.get("dict", raw)
    out: dict[str, list[str]] = {}
    for pinyin, items in table.items():
        key = normalize_pinyin(pinyin)
        if not key:
            continue
        bucket = out.setdefault(key, [])
        for it in items:
            ch = it[0] if isinstance(it, (list, tuple)) else it
            if ch and ch not in bucket:     # 去重，Rime 不喜欢重复条目
                bucket.append(ch)
    return {k: v for k, v in out.items() if v}


def write_dict_yaml(table: dict[str, list[str]], out: Path) -> int:
    lines = [
        "# Rime 词典 —— 小篆输入法",
        "# 由 tools/export_rime.py 生成，请勿手改（改了会被覆盖）",
        "---",
        "name: shuowen",
        'version: "1.0"',
        "sort: by_weight",              # 按权重排序 = 我们数据里的常用度顺序
        "use_preset_vocabulary: false",
        "...",
    ]
    n = 0
    for pinyin in sorted(table):
        chars = table[pinyin]
        top = WEIGHT_TOP
        for i, ch in enumerate(chars):
            w = max(1, top - i)
            lines.append(f"{ch}\t{pinyin}\t{w}")
            n += 1
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n


SCHEMA_YAML = """# Rime 输入方案 —— 小篆
#
# 候选窗用篆书字体渲染，上屏的是普通汉字：
#   · 你装了 ShuowenSeal.ttf  -> 候选窗里看到篆形
#   · 别人没装                -> 看到楷体汉字，照样读得懂
#
# 由 tools/export_rime.py 生成。
---
schema:
  schema_id: shuowen
  name: 小篆
  version: "1.0"
  author:
    - 严毓焕
  description: |
    《说文》小篆输入方案（拼音输入，候选窗显示篆形）。
    字形来自开元小篆（SIL OFL 1.1）、全字库说文解字、汉典补缺。
    候选窗需要安装 ShuowenSeal.ttf 才能看到篆形，否则显示普通汉字。

switches:
  - name: ascii_mode
    reset: 0
    states: [ 篆书, 西文 ]
  - name: full_shape
    reset: 0
    states: [ 半角, 全角 ]

# 候选窗字体 —— 两套键名都写上，各平台取自己认得的那一个：
#   · 桌面端（Windows 小狼毫 / macOS 鼠须管 / Linux）认 font_face
#   · 安卓同文输入法（Trime）认 candidate_font，且文件名要跟 rime/fonts/ 里的**完全一致**
# 认不出的键会被忽略，所以放一起不冲突。都没装字体时自动退回系统字体，
# 候选窗显示普通汉字 —— 退化成普通拼音输入法，不会变豆腐块。
style:
  font_face: "Shuowen Seal"
  font_point: 26
  label_font_point: 13
  candidate_font: ShuowenSeal.ttf
  candidate_text_size: 28
  comment_font: ShuowenSeal.ttf
  comment_text_size: 13
  horizontal: true
  inline_preedit: true

engine:
  processors:
    - ascii_composer
    - recognizer
    - key_binder
    - speller
    - punctuator
    - selector
    - navigator
    - express_editor
  segmentors:
    - ascii_segmentor
    - matcher
    - abc_segmentor
    - punct_segmentor
    - fallback_segmentor
  translators:
    - punct_translator
    - script_translator
  filters:
    - simplifier
    - uniquifier

speller:
  alphabet: zyxwvutsrqponmlkjihgfedcba
  delimiter: " '"
  initials: zyxwvutsrqponmlkjihgfedcba
  auto_select: true               # 唯一候选时直接上屏
  max_code_length: 48

translator:
  dictionary: shuowen
  enable_sentence: false          # 单字方案，不做整句联想
  enable_completion: true         # 支持只打一半的拼音
  enable_user_dict: false         # 不要用户词频，保持篆书字形一致
  spelling_hints: 8               # 候选旁标注拼音
  comment_format:
    - xform/^~// 

punctuator:
  import_preset: default

key_binder:
  import_preset: default
"""

DEFAULT_CUSTOM_YAML = """# 把「小篆」方案挂进 Rime 的方案列表，并让候选窗使用篆书字体。
# 放到 Rime 的用户目录下（见 README）。
---
patch:
  schema_list:
    - schema: shuowen

  # ★ 关键：候选窗字体设成 Shuowen Seal。
  #   没装这个字体时会自动退回系统字体，显示普通汉字，不会变豆腐块。
  style:
    font_face: "Shuowen Seal"
    font_point: 26
    label_font_point: 13
    inline_preedit: true
    horizontal: true
    comment_font_point: 13

  menu:
    page_size: 9
"""


TRIME_CUSTOM_YAML = """# 安卓「同文输入法」(Trime) 专用补丁。
#
# 放法：跟 shuowen.*.yaml 一起放进 rime/ 目录，然后「配置管理 → 重新部署」。
# 字体要先复制到 rime/fonts/ 下面（安卓不允许随便装系统字体），
# 且这里的文件名必须跟 rime/fonts/ 里的**完全一致**（含大小写和扩展名）。
---
patch:
  schema_list:
    - schema: shuowen

  # 安卓认的是 candidate_font；桌面端的 font_face 在安卓上不生效。
  "style/candidate_font": ShuowenSeal.ttf
  "style/comment_font": ShuowenSeal.ttf
  "style/candidate_text_size": 28
  "style/comment_text_size": 13
  "style/candidate_view_height": 38
"""


def main() -> int:
    src = ROOT / "ime" / "Resources" / "seal_dict.json"
    if not src.is_file():
        print(f"找不到词典：{src}", file=sys.stderr)
        print("（先跑 python3 tools/export_dict.py）", file=sys.stderr)
        return 1

    table = load_dict(src)
    total = sum(len(v) for v in table.values())
    print(f"词典：{len(table)} 个拼音音节，{total} 个候选项")

    outdir = ROOT / "packaging" / "rime"
    outdir.mkdir(parents=True, exist_ok=True)

    n = write_dict_yaml(table, outdir / "shuowen.dict.yaml")
    print(f"  -> shuowen.dict.yaml（{n} 条）")
    (outdir / "shuowen.schema.yaml").write_text(SCHEMA_YAML, encoding="utf-8")
    print("  -> shuowen.schema.yaml")
    (outdir / "default.custom.yaml").write_text(DEFAULT_CUSTOM_YAML, encoding="utf-8")
    print("  -> default.custom.yaml")
    (outdir / "trime.custom.yaml").write_text(TRIME_CUSTOM_YAML, encoding="utf-8")
    print("  -> trime.custom.yaml")

    # 顺带把字体复制过去，方便跟方案一起打包给别人
    font = ROOT / "build" / "ShuowenSeal.ttf"
    if font.is_file():
        dst = outdir / "ShuowenSeal.ttf"
        dst.write_bytes(font.read_bytes())
        print(f"  -> ShuowenSeal.ttf（{dst.stat().st_size / 1024 / 1024:.1f} MB）")
    else:
        print("  （build/ShuowenSeal.ttf 不存在，跳过字体复制）")

    print(f"\n产物目录：{outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
