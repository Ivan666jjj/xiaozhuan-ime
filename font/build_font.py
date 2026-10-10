#!/usr/bin/env python3
"""把汉典《说文》小篆 SVG 合成一套 TrueType 字体。

输入：``fonts/raw/{小篆码位}.svg``（由 ``tools/fetch_zdic.py`` 抓取）
输出：``build/ShuowenSeal.ttf``，字形编码在 Unicode 18.0 小篆区块 U+3D000 起。

坐标变换：SVG 是 400x400、y 轴向下；字体 unitsPerEm=1000、y 轴向上，
故对每个点做 ``(x, y) -> (k*x + ox, -k*y + oy)``。

水印过滤：汉典的 SVG 除字形外还夹带近白色（#fbfafc 一类）的角落水印路径，
按 fill 颜色剔除。
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.seal_index import SealIndex, SealDataError  # noqa: E402

VIEWBOX = 400.0
UNITS_PER_EM = 1000
MARGIN = 0.06  # 四周留白占 em 的比例

_PATH_RE = re.compile(r"<path\b[^>]*>", re.I)
_D_RE = re.compile(r'\bd="([^"]*)"')
_FILL_RE = re.compile(r'\bfill="([^"]*)"')


def is_near_white(color: str | None) -> bool:
    """判断 fill 颜色是否接近白色（汉典水印用色）。"""
    if not color:
        return False
    c = color.strip().lower()
    if c in ("none", "transparent"):
        return False
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) < 6:
            return False
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            return False
        return r > 0xE0 and g > 0xE0 and b > 0xE0
    m = re.match(r"rgba?\(([^)]*)\)", c)
    if m:
        parts = [p.strip() for p in m.group(1).replace("%", "").split(",")]
        try:
            vals = [float(p) for p in parts[:3]]
        except ValueError:
            return False
        return all(v > 224 for v in vals)
    return False


def glyph_paths(svg_text: str) -> list[str]:
    """从 SVG 文本里取出真正字形的 path 数据，剔除水印。"""
    paths: list[str] = []
    for tag in _PATH_RE.findall(svg_text):
        fill = _FILL_RE.search(tag)
        if is_near_white(fill.group(1) if fill else None):
            continue
        d = _D_RE.search(tag)
        if d and d.group(1).strip():
            paths.append(d.group(1))
    return paths


def make_transform() -> tuple[float, float, float, float, float, float]:
    """返回 svg 坐标 -> 字体坐标 的仿射矩阵 (a,b,c,d,e,f)。"""
    k = UNITS_PER_EM * (1 - 2 * MARGIN) / VIEWBOX
    span = VIEWBOX * k
    ox = (UNITS_PER_EM - span) / 2.0
    oy = UNITS_PER_EM - ox  # 注意 y 轴翻转
    return (k, 0.0, 0.0, -k, ox, oy)


def build(
    data: str | Path, srcdir: Path, out: Path, puadir: Path | None = None
) -> tuple[int, int, list[str]]:
    idx = SealIndex(data)
    matrix = make_transform()

    glyph_order = [".notdef"]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    metrics = {".notdef": (UNITS_PER_EM, 0)}
    cmap: dict[int, str] = {}
    failed: list[str] = []

    def add_glyph(codepoint: int, svg_file: Path, label: str) -> bool:
        """把一个 SVG 加进字体；返回是否成功。"""
        try:
            paths = glyph_paths(svg_file.read_text(encoding="utf-8"))
        except OSError:
            failed.append(f"{label}(读失败)")
            return False
        if not paths:
            failed.append(f"{label}(无字形路径)")
            return False
        pen = TTGlyphPen(None)
        # SVG 用三次贝塞尔，TrueType glyf 只收二次：先变换到字体坐标，再降阶为二次
        cu2qu = Cu2QuPen(pen, max_err=1.0)
        tpen = TransformPen(cu2qu, matrix)
        drew = 0
        for d in paths:
            try:
                svg_parser.parse_path(d, tpen)
                drew += 1
            except Exception:  # 单条坏路径不影响整字
                continue
        if not drew:
            failed.append(f"{label}(路径解析失败)")
            return False
        try:
            glyph = pen.glyph()
        except Exception as exc:
            failed.append(f"{label}(轮廓异常:{type(exc).__name__})")
            return False
        name = f"uni{codepoint:04X}"
        if name in glyphs:
            return False
        glyph_order.append(name)
        glyphs[name] = glyph
        metrics[name] = (UNITS_PER_EM, 0)
        cmap[codepoint] = name
        return True

    # 主区：Unicode 18.0 小篆区块 U+3D000 起
    for entry in idx.entries:
        svg_file = srcdir / f"{ord(entry.char):04X}.svg"
        if svg_file.is_file():
            add_glyph(ord(entry.char), svg_file, entry.char)

    # 补区：Unicode 无码位但汉典有篆形的常用字（PUA-A）
    if puadir and puadir.is_dir():
        for svg_file in sorted(puadir.glob("*.svg")):
            try:
                cp = int(svg_file.stem, 16)
            except ValueError:
                continue
            add_glyph(cp, svg_file, f"U+{cp:04X}")

    if len(glyph_order) <= 1:
        raise SealDataError(f"没有合成出任何字形，请检查 {srcdir}")

    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupNameTable({
        "familyName": "Shuowen Seal",
        "styleName": "Regular",
        "fullName": "Shuowen Seal Regular",
        "psName": "ShuowenSeal-Regular",
        "version": "0.1",
        "uniqueFontIdentifier": "ShuowenSeal-Regular-0.1",
        "manufacturer": "generated from Zdic Shuowen seal glyphs",
        "description": (
            "Small Seal script font encoded in the Unicode 18.0 Seal block "
            "(U+3D000..U+3FC3F). Glyphs sourced from zdic.net; personal use only."
        ),
    })
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupPost()
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))

    return len(glyph_order) - 1, len(cmap), failed


def main() -> int:
    ap = argparse.ArgumentParser(description="合成《说文》小篆字体")
    ap.add_argument("--data", default=str(ROOT / "data" / "SealSources.txt"))
    ap.add_argument("--src", default=str(ROOT / "fonts" / "raw"))
    ap.add_argument("--pua", default=str(ROOT / "fonts" / "pua"))
    ap.add_argument("--out", default=str(ROOT / "build" / "ShuowenSeal.ttf"))
    args = ap.parse_args()

    n, nc, failed = build(args.data, Path(args.src), Path(args.out), Path(args.pua))
    print(f"合成完成：{n} 个字形，cmap {nc} 项 -> {args.out}")
    if failed:
        print(f"跳过 {len(failed)} 个：", "、".join(failed[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
