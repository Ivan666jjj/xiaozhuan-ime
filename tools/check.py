#!/usr/bin/env python3
"""自检：把整条链路的关键指标打出来，方便定位问题。

    python3 tools/check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK = "\033[32m✔\033[0m"
NO = "\033[31m✘\033[0m"
WARN = "\033[33m!\033[0m"


def main() -> int:
    print("== 字库 ==")
    raw = list((ROOT / "fonts" / "raw").glob("*.svg"))
    pua = list((ROOT / "fonts" / "pua").glob("*.svg"))
    print(f"  主区 SVG(U+3Dxxx): {len(raw)}   补区 SVG(PUA): {len(pua)}")

    print("== 字体 ==")
    fp = ROOT / "build" / "ShuowenSeal.ttf"
    if fp.is_file():
        from fontTools.ttLib import TTFont
        f = TTFont(fp)
        cmap = f.getBestCmap()
        seal = sum(1 for c in cmap if 0x3D000 <= c <= 0x3FC3F)
        pua_n = sum(1 for c in cmap if 0xF0000 <= c <= 0xF0000 + (0x9FFF - 0x3400))
        print(f"  {OK} {fp.name}  {fp.stat().st_size/1024/1024:.1f} MB")
        print(f"     字形 {f['maxp'].numGlyphs}，cmap {len(cmap)}（主区 {seal} + 补区 {pua_n}）")
        if seal == 0:
            print(f"  {NO} 字体里没有小篆码位，输入法会显示成方块")
    else:
        print(f"  {NO} 缺少 {fp}，先跑 python3 font/build_font.py")
        return 1

    print("== 词典 ==")
    dp = ROOT / "ime" / "Resources" / "seal_dict.json"
    if dp.is_file():
        d = json.loads(dp.read_text(encoding="utf-8"))
        meta = d["meta"]
        print(f"  {OK} {dp.name}  {dp.stat().st_size/1024:.0f} KB")
        print(f"     拼音 {meta['pinyinCount']}，主区候选 {meta['sealCount']}，补区候选 {meta['puaCount']}")
    else:
        print(f"  {NO} 缺少 {dp}，先跑 python3 tools/export_dict.py")
        return 1

    print("== 转换内核 ==")
    from core.zhuan import ZhuanEngine
    eng = ZhuanEngine()
    print(f"  篆形总数 {eng.seal_count}，可查汉字 {eng.index.modern_count}")
    for py, want in [("shui", "水"), ("ren", "人"), ("shan", "山"), ("xiao", "小")]:
        cs = eng.candidates(py, limit=3)
        got = "".join(c.hanzi for c in cs)
        mark = OK if cs and cs[0].hanzi == want else WARN
        print(f"  {mark} {py:6s} -> {got}")
    for ch in "水说小二人":
        s = eng.char_to_seal(ch)
        kind = "补区" if s and ZhuanEngine.is_pua(s) else "主区"
        print(f"     {ch} -> {('U+%04X[%s]' % (ord(s), kind)) if s else '无篆形'}")

    print("== 系统安装 ==")
    app = Path.home() / "Library" / "Input Methods" / "ShuowenIME.app"
    font = Path.home() / "Library" / "Fonts" / "ShuowenSeal.ttf"
    print(f"  {OK if app.is_dir() else NO} 输入法 {app}")
    print(f"  {OK if font.is_file() else NO} 字体   {font}")
    try:
        out = subprocess.run(
            ["system_profiler", "SPFontsDataType"],
            capture_output=True, text=True, timeout=120).stdout
        print(f"  {OK if 'Shuowen Seal' in out else NO} 系统字体库已登记 Shuowen Seal")
    except Exception as exc:
        print(f"  {WARN} 无法查询系统字体：{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
