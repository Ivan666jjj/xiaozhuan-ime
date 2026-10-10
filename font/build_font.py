#!/usr/bin/env python3
"""从「全字库说文解字」字型合成小篆字体。

输入
----
``font/ebas/EBAS-Shuowen.ttf``
    台湾「全字库说文解字」TrueType 字型（CMEX 制作，2004）。
    收字 6,738 个汉字，字形编码在 CJK 基本区（现代汉字码位，非超 BMP）。
    授权：政府资料开放授权条款第 1 版，个人与企业均可免费使用。

``data/SealSources.txt``
    Unicode 18.0 小篆区块的 ``kSEAL_MCJK`` 对应表（小篆码位 ↔ 现代汉字）。

输出
----
``build/ShuowenSeal.ttf``
    **主区**  Unicode 18.0 小篆区块 ``U+3D000..U+3FC3F``
    **补区**  PUA-A（``U+F0000 + 汉字码位 - 0x3400``），收 Unicode 无码位的《说文》字

``data/glyph_coverage.json``
    字形覆盖表，供 ``core/zhuan.py`` 判断某字到底打不打得出。

关键实现说明
------------
EBAS 的 ``hmtx.lsb`` 与 ``glyf.xMin`` 存在大量不一致（实测「巡」差 3604、
「咄」差 682，「臦」「訌」等共 33 字），而 ``TTFont.getGlyphSet()`` 拿到的字形
在 ``draw()`` 时会把 lsb 当水平偏移用，使这些字整体错位。因此本脚本一律用
``glyf[gn].draw(pen, glyf)`` 取轮廓（offset 默认 0，即真实轮廓坐标），
重建时再令 ``hmtx.lsb == 新字形 xMin``，与新字形自洽。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.roundingPen import RoundingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.seal_index import SealDataError, SealIndex  # noqa: E402

#: 目标 em 大小
UNITS_PER_EM = 1000
#: 字面占 em 的比例（四周留白各 6%）
CONTENT_RATIO = 0.88
#: 用 1%~99% 分位确定内容框，避免个别超宽字形把整体压小
QUANTILE_LO, QUANTILE_HI = 0.01, 0.99

#: 补区 PUA 公式（与 core/zhuan.py、tools/fetch_all.py 保持一致）
PUA_BASE = 0xF0000
PUA_ORIGIN = 0x3400

FAMILY = "Shuowen Seal"


def source_codes(eb_cmap: dict[int, str]) -> list[int]:
    """EBAS 里真正的汉字码位（跳过 ASCII/控制字符）。"""
    return sorted(cp for cp in eb_cmap if 0x4E00 <= cp <= 0x9FFF)


def compute_matrix(glyf, eb_cmap: dict[int, str], codes: list[int]) -> tuple[float, ...]:
    """按内容框分位数求 SVG->字体 的仿射矩阵 (a,b,c,d,e,f)。

    EBAS 坐标已是 y 轴向上，因此无需翻转，只做等比缩放 + 居中平移。
    """
    xs0: list[int] = []
    ys0: list[int] = []
    xs1: list[int] = []
    ys1: list[int] = []

    for cp in codes:
        bp = BoundsPen(None)
        try:
            glyf[eb_cmap[cp]].draw(bp, glyf)
        except Exception:
            continue
        if bp.bounds is None:
            continue
        x0, y0, x1, y1 = bp.bounds
        xs0.append(x0)
        ys0.append(y0)
        xs1.append(x1)
        ys1.append(y1)

    if not xs0:
        raise SealDataError("EBAS 里没量到任何字形边界，字体文件可能损坏")

    def q(values: list[int], p: float) -> float:
        ordered = sorted(values)
        return float(ordered[min(len(ordered) - 1, int(len(ordered) * p))])

    cx0, cx1 = q(xs0, QUANTILE_LO), q(xs1, QUANTILE_HI)
    cy0, cy1 = q(ys0, QUANTILE_LO), q(ys1, QUANTILE_HI)

    span_w, span_h = cx1 - cx0, cy1 - cy0
    target = UNITS_PER_EM * CONTENT_RATIO
    scale = target / max(span_w, span_h)
    ox = (UNITS_PER_EM - span_w * scale) / 2.0 - cx0 * scale
    oy = (UNITS_PER_EM - span_h * scale) / 2.0 - cy0 * scale

    print(f"  内容框 x[{cx0:.0f},{cx1:.0f}] y[{cy0:.0f},{cy1:.0f}] "
          f"({span_w:.0f}×{span_h:.0f})  缩放 {scale:.4f}")
    return (scale, 0.0, 0.0, scale, ox, oy)


def build(ebas: Path, data: Path, out: Path, coverage_out: Path | None) -> dict[str, int]:
    eb = TTFont(str(ebas), fontNumber=0)
    eb_glyf = eb["glyf"]
    eb_cmap = eb.getBestCmap()
    if not eb_cmap:
        raise SealDataError(f"{ebas} 没有可用的 cmap")

    codes = source_codes(eb_cmap)
    print(f"EBAS 汉字：{len(codes)} 个")

    idx = SealIndex(data)
    print(f"Unicode 小篆条目：{len(idx.entries)} 个")

    # ---- 主区：Seal 码位 -> EBAS 汉字 -----------------------------
    seal_map: dict[int, int] = {}
    for e in idx.entries:
        modern = ord(e.modern)
        if modern in eb_cmap:
            seal_map[ord(e.char)] = modern
    print(f"主区可编码：{len(seal_map)} 个 Seal 码位（字形去重后 "
          f"{len(set(seal_map.values()))} 个）")

    # ---- 补区：EBAS 有字形、但主区未覆盖的汉字 ---------------------
    covered = set(seal_map.values())
    pua_map = {
        cp: PUA_BASE + (cp - PUA_ORIGIN)
        for cp in codes
        if cp not in covered
    }
    print(f"补区可编码：{len(pua_map)} 个汉字")

    matrix = compute_matrix(eb_glyf, eb_cmap, codes)

    # ---- 提取并重编码字形 ----------------------------------------
    glyph_order: list[str] = [".notdef"]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    cmap: dict[int, str] = {}
    cache: dict[int, str] = {}  # EBAS 汉字码位 -> 新字形名

    def glyph_for(modern_cp: int) -> str:
        """取 EBAS 字形、变换后登记为新字形；同一汉字只做一次。"""
        name = cache.get(modern_cp)
        if name is not None:
            return name
        pen = TTGlyphPen(None)
        # 顺序要留意：先变换再取整，保证落盘坐标是整数
        eb_glyf[eb_cmap[modern_cp]].draw(TransformPen(RoundingPen(pen), matrix), eb_glyf)
        name = f"uni{modern_cp:04X}"
        glyph_order.append(name)
        glyphs[name] = pen.glyph()
        cache[modern_cp] = name
        return name

    for seal_cp in sorted(seal_map):
        cmap[seal_cp] = glyph_for(seal_map[seal_cp])
    for modern_cp in sorted(pua_map):
        cmap[pua_map[modern_cp]] = glyph_for(modern_cp)

    if len(glyph_order) <= 1:
        raise SealDataError("没有合成出任何字形")

    # ---- 组装字体 -------------------------------------------------
    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)  # 顺带算好 xMin/yMin
    metrics = {name: (UNITS_PER_EM, getattr(glyphs[name], "xMin", 0)) for name in glyph_order}
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupNameTable({
        "familyName": FAMILY,
        "styleName": "Regular",
        "fullName": f"{FAMILY} Regular",
        "psName": "ShuowenSeal-Regular",
        "version": "1.0",
        "uniqueFontIdentifier": "ShuowenSeal-Regular-1.0",
        "manufacturer": "Glyphs from QuanZiKu Shuowen Jiezi (CMEX)",
        "description": (
            "Small Seal script font encoded in the Unicode 18.0 Seal block "
            "(U+3D000..U+3FC3F) plus a PUA-A fallback range. "
            "Glyph outlines from the QuanZiKu Shuowen Jiezi TrueType font, "
            "released under the Taiwan Government Open Data License v1."
        ),
    })
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupPost()
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))

    stats = {
        "sealCodepoints": len(seal_map),
        "puaCodepoints": len(pua_map),
        "glyphs": len(glyph_order) - 1,
        "cmapEntries": len(cmap),
    }

    if coverage_out is not None:
        payload = {
            "source": "全字库说文解字（EBAS / CMEX）",
            "unitsPerEm": UNITS_PER_EM,
            "sealCount": len(seal_map),
            "puaCount": len(pua_map),
            "seal": "".join(chr(cp) for cp in sorted(seal_map)),
            "pua": {chr(cp): pua_map[cp] for cp in sorted(pua_map)},
        }
        coverage_out.parent.mkdir(parents=True, exist_ok=True)
        coverage_out.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"字形覆盖表 -> {coverage_out} "
              f"({coverage_out.stat().st_size / 1024:.0f} KB)")

    return stats


def verify(font_path: Path, coverage_path: Path | None) -> list[str]:
    """复核产物：lsb 是否与 xMin 一致、每个覆盖码位是否真有字形。"""
    problems: list[str] = []
    f = TTFont(str(font_path), fontNumber=0)
    glyf, hmtx, cmap = f["glyf"], f["hmtx"], f.getBestCmap()

    skew = 0
    for name in f.getGlyphOrder():
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        if hmtx[name][1] != g.xMin:
            skew += 1
            if len(problems) < 5:
                problems.append(f"{name}: lsb={hmtx[name][1]} != xMin={g.xMin}")
    if skew:
        problems.insert(0, f"{skew} 个字形 lsb 与 xMin 不一致（渲染会整体错位）")

    if coverage_path and coverage_path.is_file():
        cov = json.loads(coverage_path.read_text(encoding="utf-8"))
        missing = [f"U+{ord(c):05X}" for c in cov["seal"] if ord(c) not in cmap]
        missing += [f"U+{cp:05X}" for cp in cov["pua"].values() if cp not in cmap]
        if missing:
            problems.append(f"覆盖表里 {len(missing)} 个码位在字体里没有字形：{missing[:5]}")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="合成《说文》小篆字体（全字库版）")
    ap.add_argument("--ebas", default=str(ROOT / "font" / "ebas" / "EBAS-Shuowen.ttf"))
    ap.add_argument("--data", default=str(ROOT / "data" / "SealSources.txt"))
    ap.add_argument("--out", default=str(ROOT / "build" / "ShuowenSeal.ttf"))
    ap.add_argument("--coverage",
                    default=str(ROOT / "data" / "glyph_coverage.json"))
    args = ap.parse_args()

    ebas, out = Path(args.ebas), Path(args.out)
    if not ebas.is_file():
        print(f"找不到字形源：{ebas}", file=sys.stderr)
        return 1

    stats = build(ebas, Path(args.data), out, Path(args.coverage))
    print(f"\n合成完成：{stats['glyphs']} 个字形，cmap {stats['cmapEntries']} 项")
    print(f"  主区 {stats['sealCodepoints']} 个 Seal 码位，补区 {stats['puaCodepoints']} 个")
    size = out.stat().st_size / 1024 / 1024
    print(f"-> {out} ({size:.1f} MB)")

    problems = verify(out, Path(args.coverage))
    if problems:
        print("\n复核发现问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("复核通过：lsb 与 xMin 全部一致，覆盖表码位全部有字形")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
