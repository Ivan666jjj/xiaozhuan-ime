#!/usr/bin/env python3
"""生成「篆书正文 + 楷书对照」的 .docx，并把字体嵌进文档。

给一首诗（或任意短句），产出一份**对方不装字体也能看到篆形**的 Word 文档。
排版跟桌面已有的样例一致：标题（楷体）→ 篆书正文（Shuowen Seal 30pt）
→ 分隔线 → 楷书对照（14pt）。

用法：
    python3 tools/make_poem_docx.py \\
        --title "登鹳雀楼 · 王之涣" \\
        --lines "白日依山尽，黄河入海流。|欲穷千里目，更上一层楼。" \\
        --out ~/Desktop/登鹳雀楼_小篆对照_可分享.docx

要点：
* 篆书行会**去掉标点**（字体里没有标点字形，留着会回退成楷体标点，混搭难看；
  古书本来也无句读），用全角空格断句；标点只保留在楷书对照行。
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
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEAL_FONT = "Shuowen Seal"
KAI_FONT = "KaiTi"
SEAL_SIZE = 30        # 篆书正文字号
KAI_SIZE = 14         # 楷书对照字号
TITLE_SIZE = 18
SEAL_LINE_GAP = 16    # 篆书行间距（pt）
KAI_LINE_GAP = 8

#: 标点/空白：这些字符不进篆书行，也不参与字形覆盖校验
PUNCT_RE = re.compile(r"[，。！？、；：·—（）《》「」〈〉“”‘’…\s\u3000]+")


def seal_line(text: str) -> str:
    """把一行诗转成篆书行：去标点，改用全角空格断句。"""
    # 先在标点处切开，再在各小段之间插全角空格
    parts = [p for p in PUNCT_RE.split(text) if p]
    return "\u3000".join(parts)


def check_coverage(font_path: Path, texts: list[str]) -> list[str]:
    """返回字体里没有篆形的字符（空列表 = 全覆盖）。"""
    cmap = TTFont(str(font_path), lazy=True).getBestCmap()
    missing = []
    for t in texts:
        for ch in t:
            if ch in PUNCT_RE.pattern or ch.isspace():
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


def build_docx(title: str, lines: list[str], out: Path) -> None:
    seal_lines = [seal_line(l) for l in lines]

    doc = Document()

    def para(space_after: float = 0):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(space_after)
        return p

    p = para()
    style_run(p.add_run(title), KAI_FONT, TITLE_SIZE, 0x33)
    para(20)
    for line in seal_lines:
        p = para(SEAL_LINE_GAP)
        style_run(p.add_run(line), SEAL_FONT, SEAL_SIZE, 0x1A)
    para(22)
    p = para(14)
    style_run(p.add_run("—" * 22), KAI_FONT, 10, 0xAA)
    for line in lines:
        p = para(KAI_LINE_GAP)
        style_run(p.add_run(line), KAI_FONT, KAI_SIZE, 0x55)

    doc.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成篆书/楷书对照 docx 并嵌入字体")
    ap.add_argument("--title", required=True, help="标题，如「登鹳雀楼 · 王之涣」")
    ap.add_argument("--lines", required=True,
                    help="诗句，用 | 分隔每一行（带标点即可，篆书行会自动去标点）")
    ap.add_argument("--out", required=True, help="输出 .docx（嵌入字体后的最终文件）")
    ap.add_argument("--font", default=str(ROOT / "build" / "ShuowenSeal.ttf"),
                    help="字形源字体（默认 build/ShuowenSeal.ttf）")
    ap.add_argument("--installed-font", default=str(Path.home() / "Library/Fonts/ShuowenSeal.ttf"),
                    help="用于覆盖校验的已安装字体（默认 ~/Library/Fonts/ShuowenSeal.ttf）")
    args = ap.parse_args()

    lines = [l.strip() for l in args.lines.split("|") if l.strip()]
    if not lines:
        print("错误：--lines 为空", file=sys.stderr)
        return 1

    font_for_check = Path(args.installed_font)
    if not font_for_check.is_file():
        font_for_check = Path(args.font)

    # 1. 覆盖校验（含标题，缺字直接失败）
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
    build_docx(args.title, lines, tmp)
    print(f"✔ 已生成正文 → {tmp}")

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
