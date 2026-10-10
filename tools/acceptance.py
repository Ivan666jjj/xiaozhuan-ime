#!/usr/bin/env python3
"""验收测试：逐项检查「小焕的小篆输入法」是否真的可用。

    python3 tools/acceptance.py

覆盖：字体 / 输入法 bundle / 系统注册 / 拼音引擎 / 部件引擎 /
540 部检索 / 分发包。结束时给出通过数与失败明细。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
APP = HOME / "Library" / "Input Methods" / "小焕的小篆输入法.app"
FONT_INSTALLED = HOME / "Library" / "Fonts" / "ShuowenSeal.ttf"
ZIP = ROOT / "dist" / "小焕的小篆输入法-macOS.zip"

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "\033[32m✔\033[0m" if cond else "\033[31m✘\033[0m"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""))


def run(args, cwd=None):
    # errors="replace"：unzip -l 输出里含中文文件名的原始字节，未必是合法 UTF-8
    return subprocess.run(args, capture_output=True, text=True,
                          errors="replace", cwd=cwd or ROOT)


def main() -> int:
    print("=" * 62)
    print("  小焕的小篆输入法 · 验收测试")
    print("=" * 62)

    print("\n[1] 字体")
    check("字体已安装到 ~/Library/Fonts", FONT_INSTALLED.is_file(),
          str(FONT_INSTALLED))
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(str(ROOT / "build" / "ShuowenSeal.ttf"))
        cmap = f.getBestCmap()
        seal = sum(1 for c in cmap if 0x3D000 <= c <= 0x3FC3F)
        pua = sum(1 for c in cmap if 0xF0000 <= c <= 0xF0000 + (0x9FFF - 0x3400))
        check("字体含小篆区块字形", seal > 5000, f"主区 {seal} 个")
        check("字体含补区字形", pua > 500, f"补区 {pua} 个")
        check("字形总数达标", f["maxp"].numGlyphs > 8000, f"{f['maxp'].numGlyphs} 字形")
    except Exception as exc:
        check("字体可解析", False, str(exc))

    out = run(["system_profiler", "SPFontsDataType"]).stdout
    check("系统字体库已登记 Shuowen Seal", "Shuowen Seal" in out)

    print("\n[2] 输入法 bundle")
    check("bundle 装在 ~/Library/Input Methods", APP.is_dir())
    check("Info.plist 存在", (APP / "Contents/Info.plist").is_file())
    check("可执行文件存在且有执行权限",
          (APP / "Contents/MacOS/ShuowenIME").is_file()
          and (APP / "Contents/MacOS/ShuowenIME").stat().st_mode & 0o111 != 0)
    check("词典随包分发", (APP / "Contents/Resources/seal_dict.json").is_file())
    check("字体随包分发", (APP / "Contents/Resources/ShuowenSeal.ttf").is_file())
    plist = (APP / "Contents/Info.plist").read_text(encoding="utf-8", errors="replace")
    check("包类型为 APPL", "<string>APPL</string>" in plist)
    check("输入模式声明在 ComponentInputModeDict 内", "ComponentInputModeDict" in plist)
    check("控制器类已声明", "SealInputController" in plist)
    check("显示名为「小焕的小篆输入法」", "小焕的小篆输入法" in plist)

    print("\n[3] 系统注册（TIS）")
    tis = Path("/tmp/tis4")
    if tis.is_file():
        o = run([str(tis)]).stdout
        check("系统已识别 ShuowenSeal 输入源", "ShuowenSeal" in o)
        check("显示名为「小焕的小篆输入法」", "小焕的小篆输入法" in o)
    else:
        check("TIS 检查工具可用", False, "缺 /tmp/tis4（可跳过）")

    print("\n[4] 拼音引擎")
    r = run([sys.executable, "zhuan.py", "--limit", "3", "shui", "ren", "shan"])
    o = r.stdout
    check("shui → 水", "水" in o, o.split("\n")[0][:50] if o else "")
    check("ren → 人", "人" in o)
    r2 = run([sys.executable, "zhuan.py", "--codepoints", "--limit", "1", "shui"])
    check("输出真实小篆码位（U+3D 区块）", bool(re.search(r"U\+3[DE][0-9A-F]{3}", r2.stdout)),
          r2.stdout.strip()[:40])
    r3 = run([sys.executable, "zhuan.py", "--strict", "--text", "的"])
    check("--strict 缺字时非零退出", r3.returncode != 0, f"rc={r3.returncode}")

    print("\n[5] 部件引擎")
    r = run([sys.executable, "compose/cli.py", "水工"])
    check("水工 → 江", "江" in r.stdout, r.stdout.strip()[:40])
    r = run([sys.executable, "compose/cli.py", "--explain", "沐"])
    check("沐 = 水 + 木", "水" in r.stdout and "木" in r.stdout, r.stdout.strip()[:40])
    r = run([sys.executable, "compose/cli.py", "--explain", "水"])
    check("独体字不被误拆", "独体" in r.stdout or "未收录" in r.stdout, r.stdout.strip()[:40])
    r = run([sys.executable, "compose/cli.py", "镕鎔"])
    check("查不到时非零退出", r.returncode != 0, f"rc={r.returncode}")

    print("\n[6] 540 部检索")
    idx_path = ROOT / "compose" / "radical_index.json"
    check("radical_index.json 存在", idx_path.is_file())
    if idx_path.is_file():
        d = json.loads(idx_path.read_text(encoding="utf-8"))
        check("部数为 540", d.get("count") == 540, f"实际 {d.get('count')}")
        tot = sum(len(x["members"]) for x in d["radicals"])
        check("成员总数 == 小篆码位数 11328", tot == 11328, f"实际 {tot}")
        first = [x["radical"] for x in d["radicals"][:5]]
        check("部序按《说文》原序（一 丄 示 三 王）",
              first == ["一", "丄", "示", "三", "王"], str(first))
    r = run([sys.executable, "compose/cli.py", "--radical", "水"])
    check("--radical 水 可用", "水部" in r.stdout and "411" in r.stdout,
          r.stdout.strip().split("\n")[0][:40])
    r = run([sys.executable, "compose/cli.py", "--radicals"])
    check("--radicals 列出 540 部", "540" in r.stdout)

    print("\n[7] 分发包")
    check("分发包存在", ZIP.is_file(),
          f"{ZIP.stat().st_size/1024/1024:.1f} MB" if ZIP.is_file() else "")
    if ZIP.is_file():
        o = run(["unzip", "-l", str(ZIP)]).stdout
        check("包含 .app", ".app/Contents/MacOS/ShuowenIME" in o)
        check("包含字体", "ShuowenSeal.ttf" in o)
        check("包含安装脚本", "install.sh" in o)
    r = run([sys.executable, "tools/check.py"])
    check("工程自检 tools/check.py 通过", r.returncode == 0)

    print("\n" + "=" * 62)
    print(f"  通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("  失败明细：")
        for n in FAIL:
            print(f"    - {n}")
    print("=" * 62)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
