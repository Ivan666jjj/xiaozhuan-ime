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

# Info-ZIP（macOS 自带 3.0）不把非 ASCII 文件名标成 UTF-8，中文名条目在
# Windows / 部分安卓解压工具里会变成乱码。改用 Python 打包，并保留符号链接。
# 用法：zip_utf8 <父目录> <要打包的子目录名> <输出 zip>
zip_utf8() {
  local parent="$1" name="$2" out="$3"
  rm -f "$out"
  python3 - "$parent" "$name" "$out" <<'PY'
import os, stat, sys, zipfile

parent, name, out = sys.argv[1], sys.argv[2], sys.argv[3]
top = os.path.join(parent, name)


def as_link(arc, target):
    zi = zipfile.ZipInfo(arc)
    zi.create_system = 3                      # unix
    zi.external_attr = (stat.S_IFLNK | 0o777) << 16
    return zi


with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for root, dirs, files in os.walk(top):
        dirs.sort()
        for d in list(dirs):
            p = os.path.join(root, d)
            if os.path.islink(p):             # 目录符号链接照原样存
                z.writestr(as_link(os.path.relpath(p, parent) + "/", os.readlink(p)),
                           os.readlink(p))
                dirs.remove(d)
        for f in sorted(files):
            full = os.path.join(root, f)
            arc = os.path.relpath(full, parent)
            if os.path.islink(full):
                z.writestr(as_link(arc, os.readlink(full)), os.readlink(full))
            else:
                z.write(full, arc)
PY
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
  # 授权声明 —— OFL 与 OGDL 都要求随字体署名，必须打进分发包
  cp "$ROOT/packaging/字形来源与授权.md" "$STAGE/字形来源与授权.md"
  cp "$ROOT/packaging/KaiyuanSeal-OFL.txt" "$STAGE/KaiyuanSeal-OFL.txt"
  cp "$ROOT/THIRD_PARTY_NOTICES.md" "$STAGE/第三方来源声明.md"
  cp "$ROOT/LICENSE" "$STAGE/LICENSE.txt"
  echo "==> 已附授权声明：MIT（代码）/ OFL（开元小篆）/ OGDL（全字库）"
  chmod +x "$STAGE/install.sh"
  zip_utf8 "$DIST" "小焕的小篆输入法" "$DIST/小焕的小篆输入法-macOS.zip"
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
  # 这个包里带字体（23.6 MB），OFL 与 OGDL 都要求随字体附上声明，
  # 所以打包前把两份声明拷进 staging（不污染 packaging/rime/ 工作区）。
  local STAGE="$ROOT/build/rime-dist"
  rm -rf "$STAGE"; mkdir -p "$STAGE/rime"
  cp -R "$ROOT/packaging/rime/." "$STAGE/rime/"
  cp "$ROOT/packaging/KaiyuanSeal-OFL.txt" "$STAGE/rime/"
  cp "$ROOT/packaging/字形来源与授权.md" "$STAGE/rime/"
  mkdir -p "$ROOT/dist"
  zip_utf8 "$STAGE" "rime" "$ROOT/dist/小篆-Rime方案.zip"
  echo "==> $ROOT/dist/小篆-Rime方案.zip（含 OFL 全文与字形来源声明）"
  du -sh "$ROOT/dist/小篆-Rime方案.zip"
  echo
  echo "用法见 zip 里的 README.md（两个平台各五步）"
}

# 发布专用：先重建「不含汉典」的合规字体，再打包两个平台的分发包。
# 汉典字形授权仅到「个人使用」，对外分发必须排除 —— 详见 packaging/字形来源与授权.md
do_publish() {
  # 先把当前（自用，含汉典）字体留一份，方便发布后切回来
  if [ -f "$ROOT/build/$FONT" ] && [ ! -f "$ROOT/build/ShuowenSeal-full.ttf" ]; then
    cp "$ROOT/build/$FONT" "$ROOT/build/ShuowenSeal-full.ttf"
    echo "==> 当前字体已另存为 build/ShuowenSeal-full.ttf（自用版，含汉典）"
  fi
  echo "==> 重建合规字体（--no-zdic：不含汉典字形，可自由分发）"
  # 覆盖表写到 build/ 下另存，免得把仓库里那份（跟自用字体配套）改掉
  python3 "$ROOT/font/build_font.py" --no-zdic \
    --coverage "$ROOT/build/glyph_coverage-compliant.json" || return 1
  do_package
  do_rime
  cat <<'TIP'

────────────────────────────────────────────
发布包已生成（用的是不含汉典的合规字体）：
  dist/小焕的小篆输入法-macOS.zip
  dist/小篆-Rime方案.zip

⚠️  build/ShuowenSeal.ttf 现在也是合规版。
    想换回自用版（含汉典，篆形更全）：
        cp build/ShuowenSeal-full.ttf build/ShuowenSeal.ttf && ./build.sh font
────────────────────────────────────────────
TIP
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
  publish)   do_publish ;;
  *) echo "用法: $0 {build|install|uninstall|font|package|rime|publish}"; exit 1 ;;
esac
