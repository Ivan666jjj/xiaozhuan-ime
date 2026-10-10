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
        check("字形总数达标（全字库共 6,738 汉字）", f["maxp"].numGlyphs >= 6700, f"{f['maxp'].numGlyphs} 字形")
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
    tis_src = ROOT / "tools" / "tis_check.swift"
    tis_bin = Path("/tmp/tis_check")
    if not tis_bin.is_file() and tis_src.is_file():
        r = run(["swiftc", "-O", "-o", str(tis_bin), str(tis_src)])
        check("TIS 检查工具编译通过", tis_bin.is_file(), r.stderr[:60])
    if tis_bin.is_file():
        r = run([str(tis_bin)])
        o = r.stdout
        check("系统已识别 ShuowenSeal 输入源", "ShuowenSeal" in o)
        check("显示名为「小焕的小篆输入法」", "小焕的小篆输入法" in o)
        check("属于键盘类输入法（系统设置里会显示）", r.returncode == 0,
              o.strip().split("\n")[-1][:56])
        # 输入模式名必须是友好名而不是 ID 本身。
        # 显示成 "com.xxx.yyy.Seal" 说明系统没解析出该模式的元数据 ——
        # 这时即使 TIS 收录了它，系统设置里也不会出现、也切不过去。
        mode_line = next((l for l in o.split("\n") if "TISKeyboardInputMode" in l
                          or l.strip().endswith("TISTypeKeyboardInputMode")), "")
        mode_name = mode_line.split("|")[1].strip() if "|" in mode_line else ""
        check("输入模式显示为友好名（不是 ID 本身）",
              bool(mode_name) and not mode_name.startswith("com."),
              f"模式名 = {mode_name or '?'}")
    else:
        check("TIS 检查工具可用", False, "需要 swiftc 编译 tools/tis_check.swift")

    # 关键：TIS 认得 ≠ 用户在系统设置里看得到。
    # 必须确认它进了「已启用输入源」列表，否则用户会在设置里找不到而以为装失败。
    # 最关键的验收项：IMK 必须接受这个输入法注册 XPC 端点。
    # 签名 identifier 与 bundle id 不一致时，imklaunchagent 会在日志里写
    # "...signing-id=ShuowenIME ... rejected"，输入法虽被 TIS 收录却永远激活不了
    # （系统设置里看不到、切不过去）。这一项必须在实机跑。
    codesign_id = run(["codesign", "-dv", str(APP)]).stderr
    check("签名 identifier 等于 bundle id",
          "Identifier=com.local.inputmethod.ShuowenSeal" in codesign_id,
          next((l for l in codesign_id.split("\n") if l.startswith("Identifier=")), "?"))

    exe = APP / "Contents" / "MacOS" / "ShuowenIME"
    if exe.is_file():
        import time as _t
        proc = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        _t.sleep(5)
        imklog = run(["log", "show", "--last", "30s", "--predicate",
                      'process == "imklaunchagent"']).stdout
        proc.terminate()
        relevant = [l for l in imklog.split("\n") if "setIMKXPCEndpoint" in l]
        # 成功时日志形如：
        #   "Received setIMKXPCEndpoint:forBundleIdentifier: from InputMethod, endpoint=..."
        # 其中并不含 bundle id（endpoint 被系统脱敏成 <private>）；
        # 失败时形如：
        #   "...(signing-id=ShuowenIME) attempted to register endpoint for <private>, rejected"
        # 所以判据是「有没有 rejected」，而非「有没有出现名字」。
        rejected = [l for l in relevant if "rejected" in l.lower()]
        accepted = [l for l in relevant if "received setimkxpcendpoint" in l.lower()]
        check("IMK 接受 XPC 端点注册（不被 rejected）",
              not rejected and bool(accepted),
              (rejected[-1][-70:] if rejected
               else (accepted[-1][-58:] if accepted else "未捕获到注册事件")))

    # 最关键的一步：TISRegisterInputSource。
    # 只把 .app 拷进 ~/Library/Input Methods/ 系统不会注册它，
    # 必须由 app 自己调用该 API，否则永远不出现在系统设置里。
    exe2 = APP / "Contents" / "MacOS" / "ShuowenIME"
    if exe2.is_file():
        reg = run([str(exe2), "--register-input-source"])
        check("TISRegisterInputSource 注册成功", reg.returncode == 0,
              (reg.stdout or reg.stderr).strip()[:56])
        st = run([str(exe2), "--status-input-source"])
        check("注册后能找到输入模式且已启用",
              "找到输入模式" in st.stdout and "true" in st.stdout,
              st.stdout.replace("\n", " / ")[:70])

    imported = run([sys.executable, "tools/enable_inputmethod.py"])
    check("enable_inputmethod.py 可运行", imported.returncode == 0,
          imported.stdout.strip()[:40])
    prefs = run(["defaults", "read", "com.apple.HIToolbox",
                 "AppleEnabledInputSources"]).stdout
    check("出现在系统输入法启用列表（系统设置里可见）",
          "ShuowenSeal" in prefs,
          "不在列表里 → 用户会在系统设置中找不到")

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
