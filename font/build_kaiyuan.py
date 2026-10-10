#!/usr/bin/env python3
"""开元小篆 SVG -> TrueType，供 build_font.py 当作**优先**字形源。

开元小篆（github.com/frankslin/kaiyuan-small-seal-font，SIL OFL 1.1）把《说文》
公版刻本扫描切字、描摹成 SVG，覆盖 Unicode 18.0 篆书区 U+3D000..U+3FC3F 全部
11,328 个码位，每个字形都带刻本出处。作者自家字型**尚未发行**（仍在逐字人工审核），
所以这一步由我们自己做。

坐标系：开元的 viewBox 是 `0 -880 1000 1000`，字形底端落在 y=0（正好是基线），
高度中位 759。所以只要翻转 y 轴、缩放到目标字面率、把底端挪到 BASELINE_BOTTOM ——
跟全字库、汉典两套源共用同一套尺度参数。

用法：
    python3 font/build_kaiyuan.py                 # 读 fonts/kaiyuan/glyphs/
    python3 font/build_kaiyuan.py --out path.ttf

产物 `font/kaiyuan/KaiyuanSeal.ttf` 入库（约 20 MB）；原始 SVG 体积 107 MB，
与汉典素材一样走 .gitignore、可重建。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parser as svg_parser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from font.build_font import (BASELINE_BOTTOM, TARGET_GLYPH_RATIO,  # noqa: E402
                             UNITS_PER_EM)

ROOT = Path(__file__).resolve().parent.parent

#: 开元字形的高度中位数（实测；viewBox 是 1000 见方）。
#: 用中位数而不是最大值来定缩放，跟全字库/汉典两套源一个口径。
KAIYUAN_MEDIAN_H = 759.0

_PATH_D = re.compile(r'\bd="([^"]*)"')
_CODE_RE = re.compile(r"^u([0-9A-Fa-f]{5})$")


def glyph_paths(svg_text: str) -> list[str]:
    """取出 SVG 里所有非空 path 的 d 属性。"""
    return [d for d in _PATH_D.findall(svg_text) if d.strip()]


def matrix() -> tuple[float, float, float, float, float, float]:
    """SVG 坐标 -> 字体坐标。

    开元的 y 轴向下（SVG 惯例）且底端在 0；字体坐标 y 轴向上、字形坐在
    BASELINE_BOTTOM 处。所以：翻转 y 轴 -> 缩放 -> 下移到目标底端。
    """
    s = UNITS_PER_EM * TARGET_GLYPH_RATIO / KAIYUAN_MEDIAN_H
    return (s, 0.0, 0.0, -s, 0.0, BASELINE_BOTTOM * UNITS_PER_EM)


def main() -> int:
    ap = argparse.ArgumentParser(description="开元小篆 SVG -> TrueType")
    ap.add_argument("--src", default=str(ROOT / "fonts" / "kaiyuan" / "glyphs"))
    ap.add_argument("--out", default=str(ROOT / "font" / "kaiyuan" / "KaiyuanSeal.ttf"))
    ap.add_argument("--max-err", type=float, default=1.0,
                    help="三次转二次的容差；1.0 保住描摹细节，调大能减体积")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        print(f"找不到开元字形目录：{src}", file=sys.stderr)
        print("（该目录走 .gitignore，需要时从上游 clone："
              "github.com/frankslin/kaiyuan-small-seal-font）", file=sys.stderr)
        return 1

    files = sorted(src.glob("u*.svg"), key=lambda p: int(p.stem[1:], 16))
    if not files:
        print(f"{src} 里没有 uXXXXX.svg", file=sys.stderr)
        return 1
    print(f"开元字形：{len(files)} 个 SVG")

    mat = matrix()
    print(f"缩放 {mat[0]:.4f}（高度中位 {KAIYUAN_MEDIAN_H} -> "
          f"{TARGET_GLYPH_RATIO * UNITS_PER_EM:.0f}），"
          f"底端 -> {BASELINE_BOTTOM * UNITS_PER_EM:.0f}")

    glyph_order: list[str] = [".notdef"]
    glyphs: dict = {".notdef": TTGlyphPen(None).glyph()}
    cmap: dict[int, str] = {}
    failed: list[int] = []
    pts_total = 0

    for f in files:
        m = _CODE_RE.match(f.stem)
        if not m:
            continue
        cp = int(m.group(1), 16)
        paths = glyph_paths(f.read_text(encoding="utf-8"))
        if not paths:
            failed.append(cp)
            continue
        pen = TTGlyphPen(None)
        tpen = Cu2QuPen(TransformPen(pen, mat), max_err=args.max_err)
        drew = False
        for d in paths:
            try:
                svg_parser.parse_path(d, tpen)
                drew = True
            except Exception:
                continue
        g = pen.glyph() if drew else None
        if g is None or g.numberOfContours <= 0:
            failed.append(cp)
            continue
        name = f"u{cp:05X}"
        glyphs[name] = g
        glyph_order.append(name)
        cmap[cp] = name
        pts_total += len(g.coordinates)

    print(f"转换完成：成功 {len(glyph_order) - 1}，失败 {len(failed)}"
          f"（平均 {pts_total / max(1, len(glyph_order) - 1):.0f} 点）")
    if failed:
        print(f"  失败码位（前 10）：{[f'U+{c:05X}' for c in failed[:10]]}")

    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (UNITS_PER_EM, 0) for n in glyph_order})
    fb.setupHorizontalHeader(ascent=880, descent=-220)
    fb.setupNameTable({
        "familyName": "Kaiyuan Seal",
        "styleName": "Regular",
        "version": "1.0",
        "manufacturer": "Kaiyuan Small Seal Font (SIL OFL 1.1)",
        "designer": "frankslin / kaiyuan-small-seal-font",
        "description": ("Glyphs traced from public-domain woodblock editions of "
                        "Shuowen Jiezi, covering the Unicode 18.0 Seal block "
                        "(U+3D000..U+3FC3F). Licensed under SIL OFL 1.1."),
    })
    fb.setupOS2()
    fb.setupPost()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))
    print(f"-> {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
