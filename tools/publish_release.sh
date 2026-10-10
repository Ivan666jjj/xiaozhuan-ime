#!/bin/bash
# 发布 GitHub Release 并上传分发包。
#
# 为什么要手动跑：GitHub Release / 上传 asset 只能走 API，而 API 需要 token。
# token 存在系统钥匙串里（service=github.com，account=Ivan666jjj），首次读取会
# 弹窗要授权 —— 非交互环境读不到，所以这一步留给你在有界面的终端里跑。
#
#   ./build.sh publish          # 先生成 dist/ 里的两个分发包
#   ./tools/publish_release.sh  # 再发 Release
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="Ivan666jjj/xiaozhuan-ime"
TAG="v1.0.0"

# 上传到 GitHub 的 asset 名用 ASCII（asset name 会进 URL，ASCII 最省事）
ASSET_MAC="$ROOT/dist/小焕的小篆输入法-macOS.zip"
ASSET_RIME="$ROOT/dist/小篆-Rime方案.zip"
NAME_MAC="xiaozhuan-ime-macOS-v1.0.0.zip"
NAME_RIME="xiaozhuan-ime-Rime-v1.0.0.zip"

for f in "$ASSET_MAC" "$ASSET_RIME"; do
  [ -f "$f" ] || { echo "找不到分发包：$f"; echo "先跑：./build.sh publish"; exit 1; }
done

# token 来源：优先环境变量 GITHUB_TOKEN，其次系统钥匙串。
# 环境变量那条路便于自动化，也便于「用完即弃」——不必把 token 落盘。
if [ -n "${GITHUB_TOKEN:-}" ]; then
  TOKEN="$GITHUB_TOKEN"
  echo "==> 使用环境变量里的 GITHUB_TOKEN"
else
  echo "==> 从钥匙串读取 GitHub token（会弹窗，请点「允许」）"
  TOKEN=$(security find-internet-password -s github.com -w)
  [ -n "$TOKEN" ] || { echo "没读到 token"; exit 1; }
fi

CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $TOKEN" \
  https://api.github.com/user)
[ "$CODE" = "200" ] || { echo "token 无效（HTTP $CODE）"; exit 1; }
echo "    验证通过"

echo "==> 创建 release $TAG"
mkdir -p "$ROOT/build"
python3 - "$ROOT" <<'PY'
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
body = """## 小焕的小篆输入法 v1.0.0

macOS 上的小篆输入法，另附 Windows / 安卓用的 Rime 方案（同一份数据）。

### 原理

**上屏的是普通汉字，靠字体把候选窗渲染成篆形。**

- 装了字体 → 候选窗里看到篆书
- 没装 → 看到普通汉字，照样读得懂、能复制、能搜索

所以打出来的字不会因为换台机器就变豆腐块。

### 有什么

- **拼音输入**：敲 `shui` → 候选窗以篆形显示「水 说 税 睡 谁」
- **部件反查**：敲 `水工` → 反查得「江」（输出真篆形，不做字形合成）
- **《说文》540 部检索**：按原书部序查某部所辖全部字
- 候选窗字号 / 每行候选数可调（输入法菜单 → 偏好设置）

### 字形来源

[开元小篆](https://github.com/frankslin/kaiyuan-small-seal-font)（SIL OFL 1.1）
+ 台湾「全字库说文解字」（政府资料开放授权条款第 1 版）。

**本发布版不含汉典字形**（其授权仅到「个人使用」），所以《说文》未收的
114 个现代常用字（以、其、前、备…）没有篆形，候选窗会显示普通汉字。
详见包内 `字形来源与授权.md`。

### 安装

**macOS** —— 下载 `xiaozhuan-ime-macOS-v1.0.0.zip`：

1. 解压，运行 `./install.sh`
2. **注销重登一次**（macOS 对输入法的硬性要求，首次安装必须）
3. 系统设置 → 键盘 → 文字输入 → 输入法 → 编辑，添加「小焕的小篆输入法」

**Windows / 安卓** —— 下载 `xiaozhuan-ime-Rime-v1.0.0.zip`，按包内 `README.md`
分别用「小狼毫 Weasel」/「同文 Trime」，各自五步。

### 授权

代码 MIT；字体按三个字源各自授权（包内附 OFL 全文与来源声明）。
"""
json.dump({"tag_name": "v1.0.0", "target_commitish": "main",
           "name": "v1.0.0 — macOS 输入法 + Windows/安卓 Rime 方案",
           "body": body},
          open(root / "build" / "rel.json", "w", encoding="utf-8"),
          ensure_ascii=False)
PY

RID=$(curl -s -X POST -H "Authorization: token $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/releases" -d @"$ROOT/build/rel.json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id') or '')")
[ -n "$RID" ] || { echo "创建 release 失败（可能已存在，去 GitHub 删掉后重跑）"; exit 1; }
echo "    release id = $RID"

for pair in "$ASSET_MAC|$NAME_MAC" "$ASSET_RIME|$NAME_RIME"; do
  f="${pair%%|*}"; n="${pair##*|}"
  echo "==> 上传 $n"
  curl -s -X POST -H "Authorization: token $TOKEN" -H "Content-Type: application/zip" \
    --data-binary @"$f" \
    "https://uploads.github.com/repos/$REPO/releases/$RID/assets?name=$n" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('    ->', d.get('browser_download_url') or d)"
done

echo
echo "完成：https://github.com/$REPO/releases/tag/$TAG"
