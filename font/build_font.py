#!/usr/bin/env python3
"""合成小篆字体：全字库说文解字为主，汉典 SVG 补缺。

字形来源
--------
``font/ebas/EBAS-Shuowen.ttf``  —— **主来源**
    台湾「全字库说文解字」TrueType 字型（CMEX 制作），6,738 个汉字。
    授权：政府资料开放授权条款第 1 版，**个人与企业均可免费使用**。

``fonts/raw/*.svg`` ``fonts/pua/*.svg``  —— **补缺来源（可选）**
    汉典《说文》小篆字形（`img.zdic.net/swxz/`），8,799 个。
    仅覆盖全字库没收的字。**授权仅到「个人使用」**，分发/商用请加 ``--no-zdic``。

编码目标
--------
**主区**  Unicode 18.0 小篆区块 ``U+3D000..U+3FC3F``
**补区**  PUA-A（``U+F0000 + 汉字码位 - 0x3400``），收 Unicode 无码位的《说文》字

输出
----
``build/ShuowenSeal.ttf``      主区 + 补区的小篆字体
``data/glyph_coverage.json``   字形覆盖表（哪些字真打得出来），供 ``core/zhuan.py`` 过滤

关键实现说明
------------
1. **EBAS 的 hmtx.lsb 与 glyf.xMin 有大量不一致**（实测 33 字：「巡」差 3604、
   「咄」差 682 …）。``TTFont.getGlyphSet()`` 拿到的字形在 ``draw()`` 时会把差值
   当水平偏移用，FreeType 也照此渲染 —— 表现为这批字整体右移。因此一律用
   ``glyf[gn].draw(pen, glyf)`` 取轮廓（offset 默认 0，即真实轮廓坐标），
   重建时再令 ``hmtx.lsb == 新字形 xMin``。
2. 两套来源各按自己的 1%~99% 分位内容框归一化到同一个目标框，视觉大小才一致。
3. 汉典 SVG 是 y 轴向下、viewBox 400×400，需镜像 y；其边角有近白色水印路径，
   按 fill 颜色剔除。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pathops
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.roundingPen import RoundingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parser as svg_parser
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.seal_index import SealDataError, SealIndex  # noqa: E402

UNITS_PER_EM = 1000
#: 字面占 em 的比例（四周留白）。0.80 是照「第一版」的观感定的 ——
#: 那版字形小、留白多、显清秀；0.88 会把字撑得偏满。
CONTENT_RATIO = 0.80
QUANTILE_LO, QUANTILE_HI = 0.01, 0.99

PUA_BASE = 0xF0000
PUA_ORIGIN = 0x3400

FAMILY = "Shuowen Seal"

ZEBRA = "  "

_PATH_RE = re.compile(r"<path\b[^>]*>", re.I)
_D_RE = re.compile(r'\bd="([^"]*)"')
_FILL_RE = re.compile(r'\bfill="([^"]*)"')


# ---------------------------------------------------------------- SVG 工具

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
    """取出真正字形的 path 数据，剔除水印。"""
    out: list[str] = []
    for tag in _PATH_RE.findall(svg_text):
        fill = _FILL_RE.search(tag)
        if is_near_white(fill.group(1) if fill else None):
            continue
        d = _D_RE.search(tag)
        if d and d.group(1).strip():
            out.append(d.group(1))
    return out


def svg_bounds(path: Path) -> tuple[float, float, float, float] | None:
    bp = BoundsPen(None)
    try:
        for d in glyph_paths(path.read_text(encoding="utf-8")):
            svg_parser.parse_path(d, bp)
    except Exception:
        return None
    return bp.bounds


# ---------------------------------------------------------------- 笔画粗细

#: 全字库字形的**收细**量（字体单位，em=1000）。
#: 全字库的笔画天生比汉典粗不少（220px 字号下 p90 宽 12px vs 8px），
#: 既然要的是「整体细」的观感，就把粗的那边收细，而不是把细的那边加粗。
EBAS_ERODE = 9.0

#: 汉典字形的加粗量。既然整体收细，这里保持原始（0 = 不加粗）——
#: 汉典原始笔画本来就在目标粗细上。
ZDIC_DILATE = 0.0

#: 收缩被拒/失败的码位（细笔画断开或布尔运算失败时保持原样）
ERODE_REJECTED: list[int] = []
DILATE_FAILED: list[int] = []


def _ink(glyph) -> float:
    """字形墨量的粗略代理：各轮廓的包围盒面积之和。

    ⚠️ 这个代理**很粗** —— 细长笔画（一条竖）的 bbox 面积远大于真实墨量，
    收缩后必然骤降，拿它当判据会大面积误杀（实测误判 2580/9416）。
    现在只作日志参考，不再用于拒绝判断。
    """
    if glyph.numberOfContours <= 0:
        return 0.0
    coords = glyph.coordinates
    starts = [0] + [e + 1 for e in glyph.endPtsOfContours[:-1]]
    total = 0.0
    for start, end in zip(starts, glyph.endPtsOfContours):
        seg = coords[start:end + 1]
        if not seg:
            continue
        xs = [p[0] for p in seg]
        ys = [p[1] for p in seg]
        total += (max(xs) - min(xs)) * (max(ys) - min(ys))
    return total


def erode_glyph(glyph, delta: float, tag: int = 0):
    """把字形轮廓**向内**收缩 delta 单位（笔画宽度 -2δ）。

    原理同 dilate_glyph，只是最后一步用 DIFFERENCE 把「沿轮廓的带子」挖掉，
    剩下的就是细了一圈的字形。

    拒绝判据只有一条：**轮廓数暴增**（断开必然让一个轮廓变两个）。
    阈值给得很宽（×2+4），因为收缩把原本粘连的笔画分开是**好事**、不算失败 ——
    真正要防的是「一根笔画中间断掉」，那在字形轮廓上表现为极端的分裂。
    宁可有几个该拒的没拒（人工抽查能看出来），也不要大面积误杀。
    """
    if delta <= 0 or glyph.numberOfContours <= 0:
        return glyph
    try:
        before_contours = len(glyph.endPtsOfContours)

        rec = RecordingPen()
        glyph.draw(rec, None)
        orig = pathops.Path()
        rec.replay(Qu2CuPen(orig.getPen(), 0.5, all_cubic=True))
        band = pathops.Path()
        rec.replay(Qu2CuPen(band.getPen(), 0.5, all_cubic=True))
        band.stroke(2 * delta, pathops.LineCap.ROUND_CAP,
                    pathops.LineJoin.ROUND_JOIN, 4.0)
        band = _quads_to_cubics(band)
        # 同 dilate_glyph：必须 fix_winding=True，否则字腔会被填实
        # （「日」「山」「回」变实心黑块）。
        result = pathops.op(orig, band, pathops.PathOp.DIFFERENCE, fix_winding=True)
        result = _quads_to_cubics(result)
        pen = TTGlyphPen(None)
        result.draw(Cu2QuPen(pen, 1.0))
        thin = pen.glyph()

        if thin.numberOfContours <= 0:
            ERODE_REJECTED.append(tag)
            return glyph
        if len(thin.endPtsOfContours) > before_contours * 2 + 4:
            ERODE_REJECTED.append(tag)      # 轮廓数暴增 = 笔画被切断了
            return glyph
        return thin
    except Exception:
        ERODE_REJECTED.append(tag)
        return glyph


def _quads_to_cubics(src):
    """把 pathops.Path 里的 QUAD 换成 CUBIC。

    skia 的 `stroke()` 给圆弧处生成二次曲线，而 pathops 自己的 `draw()` 遇到
    QUAD 会抛 `UnsupportedVerbError: CONIC`（triplewise 那段处理不完整），
    所以先把它们显式转成三次再做布尔/导出。
    """
    dst = pathops.Path()
    pen = dst.getPen()
    cur = None
    for verb, pts in src:
        n = verb.name
        if n == "MOVE":
            pen.moveTo(pts[0]); cur = pts[0]
        elif n == "LINE":
            pen.lineTo(pts[0]); cur = pts[0]
        elif n == "CUBIC":
            pen.curveTo(pts[0], pts[1], pts[2]); cur = pts[2]
        elif n == "QUAD":
            ctrl = pts[:-1] if len(pts) > 2 else [pts[0]]
            end = pts[-1] if len(pts) > 1 else pts[0]
            if cur is None:
                cur = ctrl[0]
            c, e = ctrl[-1], end
            c1 = (cur[0] + 2 / 3 * (c[0] - cur[0]), cur[1] + 2 / 3 * (c[1] - cur[1]))
            c2 = (e[0] + 2 / 3 * (c[0] - e[0]), e[1] + 2 / 3 * (c[1] - e[1]))
            pen.curveTo(c1, c2, e); cur = e
        elif n == "CLOSE":
            pen.closePath(); cur = None
    return dst


#: 膨胀失败的码位（逐个字形容错，避免一颗老鼠屎坏一锅汤）
DILATE_FAILED: list[int] = []


def dilate_glyph(glyph, delta: float, tag: int = 0):
    """把字形轮廓向外膨胀 `delta` 单位（笔画宽度 +2δ）。

    pathops 不收 TrueType 的二次曲线（CONIC），所以先 all_cubic 转三次，
    算完再用 Cu2QuPen 转回二次。布尔运算用 `fix_winding=False`：
    stroke 的结果含 QUAD，走 fix_winding 会要求 even-odd 而报错；
    TrueType 本来就是非零环绕，不修 winding 才是对的。

    个别字形轮廓太碎或自交，布尔运算会抛 PathOpsError —— 这种情况**保持原样**，
    宁可不加粗也不能把字弄坏。
    """
    if delta <= 0 or glyph.numberOfContours <= 0:
        return glyph
    try:
        rec = RecordingPen()
        glyph.draw(rec, None)
        orig = pathops.Path()
        rec.replay(Qu2CuPen(orig.getPen(), 0.5, all_cubic=True))
        band = pathops.Path()
        rec.replay(Qu2CuPen(band.getPen(), 0.5, all_cubic=True))
        band.stroke(2 * delta, pathops.LineCap.ROUND_CAP,
                    pathops.LineJoin.ROUND_JOIN, 4.0)
        band = _quads_to_cubics(band)
        # fix_winding=True：布尔运算后必须重算轮廓绕向，否则内轮廓（字腔）会被填实
        # —— 表现是「日」「国」「回」这类带框的字变成实心黑块。
        # （QUAD 已在上面转过 CUBIC，所以不会再撞 CONIC 报错。）
        result = pathops.op(orig, band, pathops.PathOp.UNION, fix_winding=True)
        result = _quads_to_cubics(result)
        pen = TTGlyphPen(None)
        result.draw(Cu2QuPen(pen, 1.0))
        return pen.glyph()
    except Exception:
        DILATE_FAILED.append(tag)
        return glyph


def index_svg_dir(directory: Path | None) -> dict[str, Path]:
    """把 SVG 目录索成 {码位字符串: 路径}，只收体积正常的文件。"""
    out: dict[str, Path] = {}
    if not directory or not directory.is_dir():
        return out
    for f in directory.glob("*.svg"):
        if f.stat().st_size > 100:
            out[f.stem.upper()] = f
    return out


# ------------------------------------------------------------ 坐标映射

def _quantile_frame(boxes: list[tuple[float, float, float, float]]):
    """由一批包围盒求 1%~99% 分位内容框。"""
    if not boxes:
        raise SealDataError("没量到任何字形边界")
    xs0 = sorted(b[0] for b in boxes)
    ys0 = sorted(b[1] for b in boxes)
    xs1 = sorted(b[2] for b in boxes)
    ys1 = sorted(b[3] for b in boxes)
    pick = lambda v, p: float(v[min(len(v) - 1, int(len(v) * p))])
    return (pick(xs0, QUANTILE_LO), pick(ys0, QUANTILE_LO),
            pick(xs1, QUANTILE_HI), pick(ys1, QUANTILE_HI))


def _fit(frame, flip_y: bool) -> tuple[float, ...]:
    """内容框 -> 目标框 [60,940] 的仿射矩阵（整体归一化，作兜底用）。"""
    cx0, cy0, cx1, cy1 = frame
    span_w, span_h = cx1 - cx0, cy1 - cy0
    target = UNITS_PER_EM * CONTENT_RATIO
    s = target / max(span_w, span_h)
    ox = (UNITS_PER_EM - span_w * s) / 2.0 - cx0 * s
    if flip_y:
        # SVG y 轴向下：先把下边界送到目标框底部
        oy = (UNITS_PER_EM - span_h * s) / 2.0 + cy1 * s
        return (s, 0.0, 0.0, -s, ox, oy)
    oy = (UNITS_PER_EM - span_h * s) / 2.0 - cy0 * s
    return (s, 0.0, 0.0, s, ox, oy)


def glyph_matrix(bounds, flip_y: bool) -> tuple[float, ...] | None:
    """**逐字形**归一化：按该字自己的包围盒等比缩放，再居中到 em 方框中心。

    为什么必须逐字形做：原始字型的扫描/描摹字形大小相差极大
    （实测 9,921 个汉字的高度极差 943 单位，而 em 才 1000；上下位置极差 438），
    若全库共用一个缩放矩阵，排出来就是「忽大忽小、上下跳动」，
    看着像一张张插图而不是一套字 —— 这正是专业字库「修字」环节要解决的第一个问题。

    做法照业界通行的 **border normalization**：取字形最长边缩放到统一的目标边长
    （等比，不拉伸，所以笔画相对粗细不变），再把**包围盒中心**对齐到 em 中心。
    """
    if not bounds:
        return None
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    target = UNITS_PER_EM * CONTENT_RATIO
    s = target / max(w, h)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    ox = UNITS_PER_EM / 2.0 - cx * s
    if flip_y:
        oy = UNITS_PER_EM / 2.0 + cy * s          # y 轴镜像
        return (s, 0.0, 0.0, -s, ox, oy)
    oy = UNITS_PER_EM / 2.0 - cy * s
    return (s, 0.0, 0.0, s, ox, oy)


def compute_ebas_matrix(glyf, cmap: dict[int, str], codes: list[int]):
    boxes = []
    for cp in codes:
        bp = BoundsPen(None)
        try:
            glyf[cmap[cp]].draw(bp, glyf)
        except Exception:
            continue
        if bp.bounds:
            boxes.append(bp.bounds)
    frame = _quantile_frame(boxes)
    print(f"{ZEBRA}全字库内容框 x[{frame[0]:.0f},{frame[2]:.0f}] "
          f"y[{frame[1]:.0f},{frame[3]:.0f}]")
    return _fit(frame, flip_y=False)


def compute_svg_matrix(raw_files: dict[str, Path], pua_files: dict[str, Path]):
    """按抽样 SVG 的内容框定缩放，使汉典字形与全字库视觉大小一致。"""
    files = sorted(raw_files.values()) + sorted(pua_files.values())
    if not files:
        return None
    step = max(1, len(files) // 800)
    boxes = [b for b in (svg_bounds(f) for f in files[::step]) if b]
    frame = _quantile_frame(boxes)
    print(f"{ZEBRA}汉典 SVG 内容框 x[{frame[0]:.0f},{frame[2]:.0f}] "
          f"y[{frame[1]:.0f},{frame[3]:.0f}]（抽样 {len(boxes)}）")
    return _fit(frame, flip_y=True)


# ------------------------------------------------------------ 主流程

def build(ebas: Path, data: Path, out: Path, coverage_out: Path | None,
          zdic_raw: Path | None, zdic_pua: Path | None) -> dict[str, int]:
    eb = TTFont(str(ebas), fontNumber=0)
    eb_glyf = eb["glyf"]
    eb_cmap = eb.getBestCmap()
    if not eb_cmap:
        raise SealDataError(f"{ebas} 没有可用的 cmap")
    codes = sorted(cp for cp in eb_cmap if 0x4E00 <= cp <= 0x9FFF)
    print(f"全字库汉字：{len(codes)} 个")

    idx = SealIndex(data)
    print(f"Unicode 小篆条目：{len(idx.entries)} 个")

    # --- 全字库能编的码位 ---
    ebas_seal = {ord(e.char): ord(e.modern)
                 for e in idx.entries if ord(e.modern) in eb_cmap}
    ebas_covered = set(ebas_seal.values())
    ebas_pua = {cp: PUA_BASE + (cp - PUA_ORIGIN)
                for cp in codes if cp not in ebas_covered}

    # --- 汉典素材 ---
    raw_files = index_svg_dir(zdic_raw)
    pua_files = index_svg_dir(zdic_pua)
    print(f"汉典素材：主区 {len(raw_files)} 个 SVG，补区 {len(pua_files)} 个 SVG")

    ebas_matrix = compute_ebas_matrix(eb_glyf, eb_cmap, codes)
    svg_matrix = compute_svg_matrix(raw_files, pua_files) if raw_files else None

    glyph_order: list[str] = [".notdef"]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    cmap: dict[int, str] = {}

    def add_ebas(modern_cp: int, target_cp: int) -> None:
        name = f"u{target_cp:05X}"
        pen = TTGlyphPen(None)
        # **全局**矩阵：全库共用一个缩放/平移，保持字形之间的相对大小。
        # 不用逐字形归一化 —— 那会把「千」「尺」这类笔画少的字硬撑到满格，
        # 笔画密的字又因放大而笔画粘连（实测糊成一片），而且原始素材本就规整：
        # 全字库高度中位 90% em、p25~p75 只差 4%，不需要逐字纠正。
        eb_glyf[eb_cmap[modern_cp]].draw(
            TransformPen(RoundingPen(pen), ebas_matrix), eb_glyf)
        glyph_order.append(name)
        # 全字库的笔画天生偏粗，按用户要求整体收细（断笔的字自动退回原样）
        glyphs[name] = erode_glyph(pen.glyph(), EBAS_ERODE, tag=target_cp)
        cmap[target_cp] = name

    def add_svg(svg_file: Path, target_cp: int) -> bool:
        paths = glyph_paths(svg_file.read_text(encoding="utf-8"))
        if not paths:
            return False
        pen = TTGlyphPen(None)
        # 同 add_ebas：走**全局**矩阵，不做逐字形归一化。
        # 汉典素材同样规整（高度中位 82% viewBox，p25~p75 只差 1 单位），
        # 它和全字库之间那 7 个百分点的整体尺度差，由各自的全局矩阵一次性对齐。
        tpen = TransformPen(Cu2QuPen(RoundingPen(pen), max_err=1.0), svg_matrix)
        drew = 0
        for d in paths:
            try:
                svg_parser.parse_path(d, tpen)
                drew += 1
            except Exception:
                continue
        if not drew:
            return False
        name = f"u{target_cp:05X}"
        glyph_order.append(name)
        # 汉典字形比全字库细一截，加粗到接近（否则混排时粗细不匀）
        glyphs[name] = dilate_glyph(pen.glyph(), ZDIC_DILATE, tag=target_cp)
        cmap[target_cp] = name
        return True

    def link_hanzi(hanzi_cp: int, target_cp: int) -> None:
        """让**现代汉字码位**也指向同一个篆形。

        输入法上屏的是普通汉字（BMP），靠这份映射在编辑器里显示成篆形 ——
        超 BMP 的小篆码位只有装了本机器的机器才认，分享出去就是豆腐块。
        同一汉字只认第一个（正篆）。
        """
        if 0x4E00 <= hanzi_cp <= 0x9FFF and hanzi_cp not in cmap:
            name = cmap.get(target_cp)
            if name:
                cmap[hanzi_cp] = name

    def link_simplified() -> int:
        """把**简体字**也指向其繁体的篆形。

        篆书不分简繁，而《说文》用字是繁体 —— 用户打「边」也该出「邊」的篆形，
        否则字体里查不到「边」，编辑器回退成普通字形，看着就不是篆书了。
        映射取自 OpenCC 的 TSCharacters.txt（繁->简），反查成 繁->[简]。
        """
        path = ROOT / "data" / "TSCharacters.txt"
        if not path.is_file():
            return 0
        trad2simp: dict[str, list[str]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            trad, simps = parts[0].strip(), parts[1].strip()
            if trad:
                trad2simp.setdefault(trad, []).extend(simps.split())

        added = 0
        for cp in sorted(c for c in cmap if 0x4E00 <= c <= 0x9FFF):
            name = cmap[cp]
            for simp in trad2simp.get(chr(cp), ()):
                scp = ord(simp)
                if 0x4E00 <= scp <= 0x9FFF and scp not in cmap:
                    cmap[scp] = name
                    added += 1
        return added

    # --- 主区：全字库优先，汉典补缺 ---
    zdic_seal_used: list[int] = []
    zdic_seal_failed: list[int] = []
    for e in idx.entries:
        seal_cp = ord(e.char)
        made = False
        if seal_cp in ebas_seal:
            add_ebas(ebas_seal[seal_cp], seal_cp)
            made = True
        else:
            svg = raw_files.get(f"{seal_cp:04X}")
            if svg is not None and svg_matrix is not None:
                if add_svg(svg, seal_cp):
                    zdic_seal_used.append(seal_cp)
                    made = True
                else:
                    zdic_seal_failed.append(seal_cp)
        if made:
            link_hanzi(ord(e.modern), seal_cp)
    print(f"主区：全字库 {len(ebas_seal)} + 汉典补 {len(zdic_seal_used)} "
          f"= {sum(1 for c in cmap if 0x3D000 <= c <= 0x3FC3F)} 个码位")
    if zdic_seal_failed:
        print(f"{ZEBRA}（汉典 SVG 解析失败 {len(zdic_seal_failed)} 个，已跳过）")

    # --- 补区：全字库能编的汉字 + 汉典有字形的汉字 ---
    zdic_pua_used: list[str] = []
    zdic_pua_failed: list[str] = []
    for f in sorted(pua_files.values()):
        try:
            pua_cp = int(f.stem, 16)
        except ValueError:
            continue
        hanzi_cp = PUA_ORIGIN + (pua_cp - PUA_BASE)
        if not (0x3400 <= hanzi_cp <= 0x9FFF):
            continue
        if hanzi_cp in ebas_covered or hanzi_cp in ebas_pua:
            continue   # 全字库有字形，走上面那批
        if pua_cp in cmap:
            continue
        if add_svg(f, pua_cp):
            zdic_pua_used.append(chr(hanzi_cp))
            link_hanzi(hanzi_cp, pua_cp)
        else:
            zdic_pua_failed.append(chr(hanzi_cp))

    for modern_cp, pua_cp in sorted(ebas_pua.items()):
        if pua_cp in cmap:      # 已被占用（不该发生，保险起见）
            continue
        add_ebas(modern_cp, pua_cp)
        link_hanzi(modern_cp, pua_cp)

    n_simp = link_simplified()

    n_ebas_pua = len(ebas_pua)
    n_zdic_pua = len(zdic_pua_used)
    n_pua = sum(1 for c in cmap if 0xF0000 <= c <= 0xFFFFD)
    n_hanzi = sum(1 for c in cmap if 0x4E00 <= c <= 0x9FFF)
    print(f"补区：全字库 {n_ebas_pua} + 汉典补 {n_zdic_pua} = {n_pua} 个码位")
    print(f"汉字码位（BMP，输入法上屏用）：{n_hanzi} 个（其中简体补齐 {n_simp}）")
    if ERODE_REJECTED:
        print(f"{ZEBRA}全字库字形收细：{len(ERODE_REJECTED)} 个保持原样（细笔画会断）")
    if DILATE_FAILED:
        print(f"{ZEBRA}汉典字形加粗：{len(DILATE_FAILED)} 个失败（保持原样，未加粗）")
    if zdic_pua_failed:
        print(f"{ZEBRA}（汉典 SVG 解析失败 {len(zdic_pua_failed)} 个，已跳过）")

    if len(glyph_order) <= 1:
        raise SealDataError("没有合成出任何字形")

    # --- 组装字体 ---
    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)          # 顺带算好 xMin/yMin
    metrics = {n: (UNITS_PER_EM, getattr(glyphs[n], "xMin", 0)) for n in glyph_order}
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupNameTable({
        "familyName": FAMILY,
        "styleName": "Regular",
        "fullName": f"{FAMILY} Regular",
        "psName": "ShuowenSeal-Regular",
        "version": "2.0",
        "uniqueFontIdentifier": "ShuowenSeal-Regular-2.0",
        "manufacturer": "QuanZiKu Shuowen Jiezi (CMEX) + zdic.net",
        "description": (
            "Small Seal script font encoded in the Unicode 18.0 Seal block "
            "(U+3D000..U+3FC3F) plus a PUA-A fallback range. Primary glyphs from "
            "the QuanZiKu Shuowen Jiezi font (Taiwan Government Open Data License v1); "
            "remaining glyphs from zdic.net (personal use only)."
        ),
    })
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupPost()
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))

    stats = {
        "sealCodepoints": sum(1 for c in cmap if 0x3D000 <= c <= 0x3FC3F),
        "puaCodepoints": n_pua,
        "hanziCodepoints": n_hanzi,
        "zdicSeal": len(zdic_seal_used),
        "zdicPua": n_zdic_pua,
        "glyphs": len(glyph_order) - 1,
        "cmapEntries": len(cmap),
    }

    if coverage_out is not None:
        payload = {
            "source": "全字库说文解字（EBAS / CMEX）+ 汉典补缺",
            "unitsPerEm": UNITS_PER_EM,
            "sealCount": stats["sealCodepoints"],
            "puaCount": stats["puaCodepoints"],
            "hanziCount": stats["hanziCodepoints"],
            "seal": "".join(chr(c) for c in sorted(c for c in cmap
                                                   if 0x3D000 <= c <= 0x3FC3F)),
            # 键是**汉字**（不是 PUA 字符）—— core/zhuan.py 按汉字查
            "pua": {chr(PUA_ORIGIN + (c - PUA_BASE)): c
                    for c in sorted(c for c in cmap if 0xF0000 <= c <= 0xFFFFD)},
            # 输入法上屏用：现代汉字码位（字体里这些码位同样是篆形）
            "hanzi": "".join(chr(c) for c in sorted(c for c in cmap
                                                    if 0x4E00 <= c <= 0x9FFF)),
            "zdic": {
                "note": "以下码位的字形来自汉典，授权仅到个人使用；"
                        "要分发/商用请用 python3 font/build_font.py --no-zdic 重建",
                "sealCount": stats["zdicSeal"],
                "puaCount": stats["zdicPua"],
                "seal": "".join(chr(c) for c in sorted(zdic_seal_used)),
                "pua": sorted(zdic_pua_used),
            },
        }
        coverage_out.parent.mkdir(parents=True, exist_ok=True)
        coverage_out.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        print(f"字形覆盖表 -> {coverage_out} ({coverage_out.stat().st_size/1024:.0f} KB)")

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
        missing += [f"U+{ord(c):04X}" for c in cov.get("hanzi", "") if ord(c) not in cmap]
        if missing:
            problems.append(f"覆盖表里 {len(missing)} 个码位在字体里没有字形：{missing[:5]}")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="合成《说文》小篆字体")
    ap.add_argument("--ebas", default=str(ROOT / "font" / "ebas" / "EBAS-Shuowen.ttf"))
    ap.add_argument("--data", default=str(ROOT / "data" / "SealSources.txt"))
    ap.add_argument("--out", default=str(ROOT / "build" / "ShuowenSeal.ttf"))
    ap.add_argument("--coverage", default=str(ROOT / "data" / "glyph_coverage.json"))
    ap.add_argument("--zdic-raw", default=str(ROOT / "fonts" / "raw"),
                    help="汉典主区 SVG 目录（补缺用）")
    ap.add_argument("--zdic-pua", default=str(ROOT / "fonts" / "pua"),
                    help="汉典补区 SVG 目录（补缺用）")
    ap.add_argument("--no-zdic", action="store_true",
                    help="只用全字库，产出可自由分发/商用的版本")
    args = ap.parse_args()

    ebas, out = Path(args.ebas), Path(args.out)
    if not ebas.is_file():
        print(f"找不到字形源：{ebas}", file=sys.stderr)
        return 1

    zdic_raw = None if args.no_zdic else Path(args.zdic_raw)
    zdic_pua = None if args.no_zdic else Path(args.zdic_pua)

    stats = build(ebas, Path(args.data), out, Path(args.coverage), zdic_raw, zdic_pua)
    print(f"\n合成完成：{stats['glyphs']} 个字形，cmap {stats['cmapEntries']} 项")
    print(f"  主区 {stats['sealCodepoints']} 码位（其中汉典补 {stats['zdicSeal']}）")
    print(f"  补区 {stats['puaCodepoints']} 码位（其中汉典补 {stats['zdicPua']}）")
    print(f"  汉字码位 {stats['hanziCodepoints']} 个（BMP，输入法上屏用）")
    print(f"-> {out} ({out.stat().st_size/1024/1024:.1f} MB)")

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
