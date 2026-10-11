#!/usr/bin/env python3
"""生成「篆书 + 楷书对照」的 .docx，并把字体嵌进文档。

给一首诗（或任意短句），产出一份**对方不装字体也能看到篆形**的 Word 文档。

## 两种版式（--layout）

**stacked**（默认）—— 篆书整块在上、楷书整块在下，中间一条细线。
适合**欣赏**：篆书那部分完整呈现，像一幅字，不被切割。

**interlinear** —— 逐字对照：每个篆字**正下方**标出它对应的简体。
适合**认字**：「这个篆字是什么」。

    ┌──┬──┬──┬──┬──┬──┬──┐
    │白│日│依│山│尽│  │黄│   ← 篆形（标点格留空）
    ├──┼──┼──┼──┼──┼──┼──┤
    │白│日│依│山│尽│，│黄│   ← 简体
    └──┴──┴──┴──┴──┴──┴──┘

## 用法

    python3 tools/make_poem_docx.py \\
        --title "登鹳雀楼 · 王之涣" \\
        --lines "白日依山尽，黄河入海流。|欲穷千里目，更上一层楼。" \\
        --out ~/Desktop/登鹳雀楼_小篆对照_可分享.docx

    # 逐字对照版
    python3 tools/make_poem_docx.py --layout interlinear ...

## 要点

* 标题里的「·」会被自动拆开：**标题一行（26pt 加粗）、作者一行（13pt 灰）**。
  原来是同一行、同字号同字体，读者第一眼分不出主次 —— 这是朋友提的意见。
* 篆书行会**去掉标点**（字体里没有标点字形，留着会回退成楷体标点，混搭难看；
  古书本来也无句读），用全角空格断句。interlinear 版式下简体行**保留标点**。
* 生成前逐个校验字形覆盖率，缺字直接报错 —— 字体缺字时会静默回退成楷体，
  看起来就不像篆书了。
* 中文字体必须显式设 `w:eastAsia`，否则 Word 会用默认中文字体渲染。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEAL_FONT = "Shuowen Seal"
KAI_FONT = "KaiTi"

#: 标题与作者拉开层次：标题大而重、作者小而淡
#: （原来两者同字号同字体，读者第一眼分不出主次 —— 朋友实测反馈）
TITLE_SIZE = 26
AUTHOR_SIZE = 13
SEAL_SIZE = 30        # 篆书正文字号
KAI_SIZE = 14         # 楷书对照字号
SEAL_LINE_GAP = 16    # 篆书行间距（pt）
KAI_LINE_GAP = 8
INTER_SEAL_SIZE = 22  # 逐字对照版：篆形字号
INTER_KAI_SIZE = 11   # 逐字对照版：简体字号
INTER_COL_W = 26      # 逐字对照版：每格宽度（pt）

#: 标点/空白：这些字符不进篆书行，也不参与字形覆盖校验
PUNCT_RE = re.compile(r"[，。！？、；：·—（）《》「」〈〉“”‘’…\s\u3000]+")
#: 判断「单个字符是不是标点」（逐字对照版里标点格不写篆形）
PUNCT_ONE = re.compile(r"[，。！？、；：·—（）《》「」〈〉“”‘’…]")


def seal_line(text: str) -> str:
    """把一行诗转成篆书行：去标点，改用全角空格断句。"""
    parts = [p for p in PUNCT_RE.split(text) if p]
    return "\u3000".join(parts)


def split_title(title: str) -> tuple[str, str | None]:
    """把「登鹳雀楼 · 王之涣」拆成 (标题, 作者)。找不到分隔符时作者为 None。"""
    for sep in (" · ", "·", " —— ", "——", " - "):
        if sep in title:
            a, b = title.split(sep, 1)
            if a.strip() and b.strip():
                return a.strip(), b.strip()
    return title.strip(), None


def check_coverage(font_path: Path, texts: list[str]) -> list[str]:
    """返回字体里没有篆形的字符（空列表 = 全覆盖）。"""
    cmap = TTFont(str(font_path), lazy=True).getBestCmap()
    missing = []
    for t in texts:
        for ch in t:
            if PUNCT_ONE.fullmatch(ch) or ch.isspace():
                continue
            if ord(ch) not in cmap and ch not in missing:
                missing.append(ch)
    return missing


def style_run(run, font_name: str, size: float, gray: int, bold: bool = False) -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = font_name
    run.font.color.rgb = RGBColor(gray, gray, gray)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rFonts.set(qn("w:eastAsia"), font_name)      # ★ 中文必须显式设


def _para(doc, space_after: float = 0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _head(doc, title: str) -> None:
    """标题区：标题一行（大、加粗）、作者一行（小、灰）。"""
    main, author = split_title(title)
    p = _para(doc)
    style_run(p.add_run(main), KAI_FONT, TITLE_SIZE, 0x1A, bold=True)
    if author:
        p = _para(doc, 22)
        style_run(p.add_run(author), KAI_FONT, AUTHOR_SIZE, 0x6B)
    else:
        _para(doc, 22)


def build_stacked(title: str, lines: list[str], out: Path) -> None:
    """上下对照：篆书整块在上、楷书整块在下。"""
    doc = Document()
    _head(doc, title)

    for line in lines:
        p = _para(doc, SEAL_LINE_GAP)
        style_run(p.add_run(seal_line(line)), SEAL_FONT, SEAL_SIZE, 0x1A)

    p = _para(doc, 20)
    style_run(p.add_run("—" * 22), KAI_FONT, 10, 0xAA)

    for line in lines:
        p = _para(doc, KAI_LINE_GAP)
        style_run(p.add_run(line), KAI_FONT, KAI_SIZE, 0x55)

    doc.save(out)


def _cell(cell, text: str, font: str, size: float, gray: int) -> None:
    """写一个表格单元格（居中、无内边距感）。"""
    cell.width = Pt(INTER_COL_W)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    if text:
        style_run(p.add_run(text), font, size, gray)


def build_interlinear(title: str, lines: list[str], out: Path) -> None:
    """逐字对照：每个篆字正下方标它对应的简体。

    用无边框表格实现 —— 每列一个字，第一行篆形、第二行简体。
    标点在篆形行留空（字体里没有标点字形），简体行照常显示。
    """
    doc = Document()
    _head(doc, title)

    for line in lines:
        chars = list(line)
        table = doc.add_table(rows=2, cols=len(chars))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        for i, ch in enumerate(chars):
            is_punct = bool(PUNCT_ONE.fullmatch(ch))
            # 上行：篆形（标点格留空）
            _cell(table.cell(0, i), "" if is_punct else ch,
                  SEAL_FONT, INTER_SEAL_SIZE, 0x1A)
            # 下行：简体（标点淡一点）
            _cell(table.cell(1, i), ch, KAI_FONT, INTER_KAI_SIZE,
                  0x8A if is_punct else 0x44)
        # 句间留白
        p = _para(doc, 14)
        style_run(p.add_run(" "), KAI_FONT, 6, 0xF0)

    doc.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成篆书/楷书对照 docx 并嵌入字体")
    ap.add_argument("--title", required=True, help="标题，如「登鹳雀楼 · 王之涣」")
    ap.add_argument("--lines", required=True,
                    help="诗句，用 | 分隔每一行（带标点即可）")
    ap.add_argument("--out", required=True, help="输出 .docx（嵌入字体后的最终文件）")
    ap.add_argument("--layout", default="stacked", choices=["stacked", "interlinear"],
                    help="stacked=上下对照（默认，适合欣赏）；"
                         "interlinear=逐字对照（适合认字）")
    ap.add_argument("--font", default=str(ROOT / "build" / "ShuowenSeal.ttf"),
                    help="字形源字体（默认 build/ShuowenSeal.ttf）")
    ap.add_argument("--installed-font",
                    default=str(Path.home() / "Library/Fonts/ShuowenSeal.ttf"),
                    help="用于覆盖校验的已安装字体")
    args = ap.parse_args()

    lines = [l.strip() for l in args.lines.split("|") if l.strip()]
    if not lines:
        print("错误：--lines 为空", file=sys.stderr)
        return 1

    font_for_check = Path(args.installed_font)
    if not font_for_check.is_file():
        font_for_check = Path(args.font)

    # 1. 覆盖校验（含标题与作者，缺字直接失败）
    missing = check_coverage(font_for_check, [args.title] + lines)
    if missing:
        print(f"错误：字体缺这些字的篆形，会回退成楷体 —— {''.join(missing)}", file=sys.stderr)
        print("       换一首诗，或先把这些字补进字体。", file=sys.stderr)
        return 1
    print(f"✔ 覆盖校验通过（{len(set(''.join([args.title] + lines)))} 个不同字符都有篆形）")

    # 2. 生成未嵌入的 docx（放临时位置）
    out = Path(args.out).expanduser()
    tmp = out.with_name(out.stem + ".tmp-nofont.docx")
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.layout == "interlinear":
        build_interlinear(args.title, lines, tmp)
    else:
        build_stacked(args.title, lines, tmp)
    print(f"✔ 已生成正文（{args.layout} 版式）→ {tmp}")

    # 3. 嵌入字体
    from tools.embed_font_docx import embed, verify
    stats = embed(tmp, Path(args.font), SEAL_FONT, out)
    print(f"✔ 字体 {stats['fontBytes']/1024/1024:.1f} MB → 子集 "
          f"{stats['subsetBytes']/1024:.0f} KB（用到 {stats['glyphsUsed']} 个字符）")
    problems = verify(out)
    if problems:
        print("复核发现问题：", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 1
    tmp.unlink(missing_ok=True)
    print(f"✔ 复核通过，已输出 {out}（{stats['docxBytes']/1024/1024:.2f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
