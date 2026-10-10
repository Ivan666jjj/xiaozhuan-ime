#!/usr/bin/env python3
"""把「小焕的小篆输入法」加进系统输入法启用列表。

为什么需要这一步：把 .app 放进 ~/Library/Input Methods/ 之后，系统（TIS）
能识别它，但**不会自动启用**——用户得打开「系统设置 → 键盘 → 文字输入 →
输入法 → 编辑」再点 `+` 手动添加。而系统设置那个面板读的是缓存，
刚装完往往看不到，容易以为装失败了。

这里直接改 `com.apple.HIToolbox` 的 `AppleEnabledInputSources`，效果等同于
用户在 UI 里点 `+` 添加。改完重启 TextInputMenuAgent 生效。

用法：
    python3 tools/enable_inputmethod.py            # 启用
    python3 tools/enable_inputmethod.py --remove   # 从启用列表移除（卸载用）
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

BUNDLE_ID = "com.local.inputmethod.ShuowenSeal"
MODE_ID = BUNDLE_ID + ".Seal"
DOMAIN = "com.apple.HIToolbox"
KEY = "AppleEnabledInputSources"


def read_prefs() -> dict:
    """读 com.apple.HIToolbox（经 defaults export，绕开 cfprefsd 缓存）。"""
    raw = subprocess.run(["defaults", "export", DOMAIN, "-"],
                         capture_output=True).stdout
    if not raw:
        return {}
    try:
        return plistlib.loads(raw)
    except Exception as exc:
        print(f"错误：无法解析 {DOMAIN} 偏好：{exc}", file=sys.stderr)
        sys.exit(1)


def write_prefs(d: dict) -> None:
    tmp = Path("/tmp/_hitoolbox_new.plist")
    tmp.write_bytes(plistlib.dumps(d))
    r = subprocess.run(["defaults", "import", DOMAIN, str(tmp)],
                       capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"错误：写入偏好失败 {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def restart_services() -> None:
    for name in ("TextInputMenuAgent", "TextInputSwitcher", "cfprefsd"):
        subprocess.run(["killall", "-HUP", name], capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="启用/停用输入法")
    ap.add_argument("--remove", action="store_true", help="从启用列表移除")
    args = ap.parse_args()

    d = read_prefs()
    arr = d.get(KEY, [])
    hits = [x for x in arr if x.get("Bundle ID") == BUNDLE_ID]
    if args.remove:
        if not hits:
            print("未在启用列表里")
            return 0
        d[KEY] = [x for x in arr if x.get("Bundle ID") != BUNDLE_ID]
        write_prefs(d)
        restart_services()
        print("已从输入法启用列表移除")
        return 0

    if hits:
        print("已在启用列表里，无需重复添加")
        return 0

    arr.append({
        "Bundle ID": BUNDLE_ID,
        "Input Mode": MODE_ID,
        "InputSourceKind": "Input Mode",
    })
    d[KEY] = arr
    write_prefs(d)
    restart_services()
    print(f"已启用：{len(arr)} 个输入源（新增「小焕的小篆输入法」）")
    print("提示：重开一次「系统设置」窗口即可在列表里看到它。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
