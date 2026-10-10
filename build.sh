#!/bin/bash
# 小篆输入法 —— 构建 / 安装脚本
#
#   ./build.sh build      编译并组装 .app bundle
#   ./build.sh install    装到 ~/Library/Input Methods/ 并注册
#   ./build.sh uninstall  卸载
#   ./build.sh font       只安装字体到 ~/Library/Fonts/
#   ./build.sh package    生成可分发的压缩包 dist/
#
# 注：bundle 用 .app 后缀而非传统的 .inputmethod —— 与系统里已有的第三方输入法
# （QianwenIME.app、WeType.app）保持一致，这类 bundle 会被 LaunchServices 当成
# 标准应用注册，系统扫描得更积极。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="ShuowenIME"
BUNDLE="小焕的小篆输入法.app"
BUILD="$ROOT/build/ime"
DEST="$HOME/Library/Input Methods/$BUNDLE"
FONTDIR="$HOME/Library/Fonts"
FONT="ShuowenSeal.ttf"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1"; exit 1; }; }

do_build() {
  need swiftc
  [ -f "$ROOT/ime/Resources/seal_dict.json" ] || {
    echo "先跑：python3 tools/export_dict.py"; exit 1; }
  [ -f "$ROOT/build/$FONT" ] || {
    echo "先跑：python3 font/build_font.py"; exit 1; }

  rm -rf "$BUILD"
  mkdir -p "$BUILD/$BUNDLE/Contents/MacOS" "$BUILD/$BUNDLE/Contents/Resources"

  echo "==> 编译 Swift"
  swiftc -O \
    -framework Cocoa -framework InputMethodKit \
    -o "$BUILD/$BUNDLE/Contents/MacOS/$NAME" \
    "$ROOT"/ime/$NAME/*.swift

  echo "==> 组装 bundle"
  cp "$ROOT/ime/Resources/Info.plist" "$BUILD/$BUNDLE/Contents/Info.plist"
  # PkgInfo：传统 bundle 标记，系统组件扫描时会看
  printf 'APPL????' > "$BUILD/$BUNDLE/Contents/PkgInfo"
  cp "$ROOT/ime/Resources/seal_dict.json" "$BUILD/$BUNDLE/Contents/Resources/"
  cp "$ROOT/build/$FONT" "$BUILD/$BUNDLE/Contents/Resources/"
  # 本地化（影响菜单里显示的输入法名与输入模式名）
  if [ -d "$ROOT/ime/Resources/zh-Hans.lproj" ]; then
    cp -R "$ROOT/ime/Resources/zh-Hans.lproj" "$BUILD/$BUNDLE/Contents/Resources/"
  fi
  [ -f "$ROOT/ime/Resources/InfoPlist.strings" ] && \
    cp "$ROOT/ime/Resources/InfoPlist.strings" "$BUILD/$BUNDLE/Contents/Resources/"
  # 图标（系统设置里显示输入法要用到）
  [ -f "$ROOT/ime/Resources/ShuowenIME.icns" ] && \
    cp "$ROOT/ime/Resources/ShuowenIME.icns" "$BUILD/$BUNDLE/Contents/Resources/"
  [ -f "$ROOT/ime/Resources/shuowen_menu_icon.pdf" ] && \
    cp "$ROOT/ime/Resources/shuowen_menu_icon.pdf" "$BUILD/$BUNDLE/Contents/Resources/"
  # 菜单图标
  for icon in menu_16.png menu_32.png; do
    [ -f "$ROOT/ime/Resources/$icon" ] && \
      cp "$ROOT/ime/Resources/$icon" "$BUILD/$BUNDLE/Contents/Resources/"
  done
  echo "==> 完成：$BUILD/$BUNDLE"
}

do_package() {
  do_build
  local DIST="$ROOT/dist"
  local STAGE="$DIST/小焕的小篆输入法"
  rm -rf "$STAGE"; mkdir -p "$STAGE"
  cp -R "$BUILD/$BUNDLE" "$STAGE/"
  cp "$ROOT/build/$FONT" "$STAGE/"
  cp "$ROOT/packaging/install.sh" "$STAGE/"
  cp "$ROOT/packaging/使用说明.md" "$STAGE/使用说明.md"
  cp "$ROOT/tools/enable_inputmethod.py" "$STAGE/"
  chmod +x "$STAGE/install.sh"
  ( cd "$DIST" && zip -qry "小焕的小篆输入法-macOS.zip" "小焕的小篆输入法" )
  echo "==> 分发包：$DIST/小焕的小篆输入法-macOS.zip"
  du -sh "$DIST/小焕的小篆输入法-macOS.zip"
}

do_font() {
  mkdir -p "$FONTDIR"
  cp "$ROOT/build/$FONT" "$FONTDIR/"
  echo "字体已装到 $FONTDIR/$FONT"
  echo "（若 app 里还没出现，注销重登或跑：atsutil databases -remove）"
}

do_rime() {
  echo "==> 导出 Rime 方案（Windows 小狼毫 / 安卓同文）"
  python3 "$ROOT/tools/export_rime.py" || return 1
  mkdir -p "$ROOT/dist"
  ( cd "$ROOT/packaging" && zip -qry "$ROOT/dist/小篆-Rime方案.zip" rime )
  echo "==> $ROOT/dist/小篆-Rime方案.zip"
  du -sh "$ROOT/dist/小篆-Rime方案.zip"
  echo
  echo "用法见 zip 里的 README.md（两个平台各五步）"
}

do_install() {
  do_build
  rm -rf "$DEST"
  mkdir -p "$HOME/Library/Input Methods"
  cp -R "$BUILD/$BUNDLE" "$HOME/Library/Input Methods/"
  # 必须重新签名，且 identifier 要等于 bundle id。
  # 否则 imklaunchagent 会拒绝注册 XPC 端点（日志里表现为
  # "setIMKXPCEndpoint: ... signing-id=ShuowenIME ... rejected"），
  # 输入法虽被 TIS 收录却永远无法激活。
  codesign --force --deep --sign - \
    --identifier "com.local.inputmethod.ShuowenSeal" "$DEST" 2>/dev/null \
    && echo "已重新签名（identifier=com.local.inputmethod.ShuowenSeal）" \
    || echo "警告：重新签名失败"
  do_font
  # 让系统重新扫描输入法
  killall -HUP "$NAME" 2>/dev/null || true
  killall -HUP TextInputMenuAgent 2>/dev/null || true
  # 关键：必须调用 TISRegisterInputSource 注册，系统才会「认识」这个输入法。
  # 只把 .app 拷进 ~/Library/Input Methods/ 是不够的 —— 实测仅拷贝 + 重启服务 +
  # 反复注销重登，它都不会出现在系统设置的输入法列表里。
  echo "==> 注册输入法（TISRegisterInputSource）"
  if [ -x "$DEST/Contents/MacOS/ShuowenIME" ]; then
    "$DEST/Contents/MacOS/ShuowenIME" --register-input-source || true
    "$DEST/Contents/MacOS/ShuowenIME" --enable-input-source || true
  fi
  # 兜底：也写一次偏好（部分系统版本上 TIS 注册后仍需此项）
  python3 "$ROOT/tools/enable_inputmethod.py" 2>/dev/null || true
  echo
  echo "已安装到：$DEST"
  echo "下一步：系统设置 → 键盘 → 文字输入 → 输入法 → 编辑，加上「小篆输入法」"
  echo "（或注销/重登一次让系统识别新输入法）"
}

do_uninstall() {
  rm -rf "$DEST"
  rm -f "$FONTDIR/$FONT"
  killall -HUP "$NAME" 2>/dev/null || true
  echo "已卸载输入法与字体"
}

case "${1:-build}" in
  build)     do_build ;;
  install)   do_install ;;
  uninstall) do_uninstall ;;
  font)      do_font ;;
  package)   do_package ;;
  rime)      do_rime ;;
  *) echo "用法: $0 {build|install|uninstall|font|package|rime}"; exit 1 ;;
esac
