#!/bin/bash
# 小焕的小篆输入法 —— 一键安装 / 卸载
#
#   ./install.sh            安装（输入法 + 字体）
#   ./install.sh --uninstall 卸载
#
# 安装位置：
#   ~/Library/Input Methods/小焕的小篆输入法.app
#   ~/Library/Fonts/ShuowenSeal.ttf
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SRC="$ROOT/小焕的小篆输入法.app"
FONT_SRC="$ROOT/ShuowenSeal.ttf"
APP_DST="$HOME/Library/Input Methods/小焕的小篆输入法.app"
FONT_DST="$HOME/Library/Fonts/ShuowenSeal.ttf"

say() { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
ok()  { printf '\033[1;32m✔\033[0m %s\n' "$1"; }
err() { printf '\033[1;31m✘\033[0m %s\n' "$1" >&2; }

if [ "${1:-}" = "--uninstall" ]; then
  say "卸载"
  rm -rf "$APP_DST" "$FONT_DST"
  killall -HUP TextInputMenuAgent 2>/dev/null || true
  ok "已卸载输入法与字体"
  echo "（若输入法菜单里仍有残留，注销或重启一次即可）"
  exit 0
fi

[ -d "$APP_SRC" ]  || { err "找不到 $APP_SRC"; exit 1; }
[ -f "$FONT_SRC" ] || { err "找不到 $FONT_SRC"; exit 1; }

say "安装输入法到 ~/Library/Input Methods/"
mkdir -p "$HOME/Library/Input Methods"
rm -rf "$APP_DST"
cp -R "$APP_SRC" "$APP_DST"
ok "输入法已安装"

say "安装字体到 ~/Library/Fonts/"
mkdir -p "$HOME/Library/Fonts"
cp "$FONT_SRC" "$FONT_DST"
ok "字体已安装"

# 重新签名（本机 adhoc，避免 Gatekeeper 拦截）
codesign --force --deep --sign - --identifier com.local.inputmethod.ShuowenSeal "$APP_DST" 2>/dev/null \
  && ok "已重新签名" || true

# 通知系统重新扫描
killall -HUP TextInputMenuAgent 2>/dev/null || true
killall -HUP TextInputSwitcher 2>/dev/null || true

# 自动加入输入法启用列表（等同于点 + 添加）
if [ -f "$ROOT/enable_inputmethod.py" ]; then
  say "启用输入法"
  python3 "$ROOT/enable_inputmethod.py" && ok "已加入启用列表" || true
elif command -v python3 >/dev/null 2>&1 && [ -f "$ROOT/tools/enable_inputmethod.py" ]; then
  say "启用输入法"
  python3 "$ROOT/tools/enable_inputmethod.py" && ok "已加入启用列表" || true
fi

cat <<'TIP'

安装完成！

下一步：
  1. 打开「系统设置 → 键盘 → 文字输入 → 输入法 → 编辑」
  2. 添加「小焕的小篆输入法」
  3. 按 Ctrl+Space（或 Fn）切换过去，输入拼音即可（如 shui）

若列表里看不到，注销/重启一次即可。
TIP
