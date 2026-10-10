#!/bin/bash
# 发布 GitHub Release 并上传分发包。
#
# 为什么需要手动跑一次：GitHub Release / 上传 asset 只能走 API，
# 而 API 需要 token。token 存在系统钥匙串里（service=github.com，
# account=Ivan666jjj），首次读取会弹窗要授权——非交互环境下读不到，
# 所以这一步留给你在有界面的终端里跑。
#
#   ./tools/publish_release.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="Ivan666jjj/xiaozhuan-ime"
TAG="v1.0.0"
ASSET="$ROOT/releases/xiaohuan-xiaozhuan-ime-macOS-v1.0.0.zip"
ASSET_NAME="xiaohuan-xiaozhuan-ime-macOS-v1.0.0.zip"

[ -f "$ASSET" ] || { echo "找不到分发包：$ASSET"; exit 1; }

echo "==> 从钥匙串读取 GitHub token（会弹窗，请点「允许」）"
TOKEN=$(security find-internet-password -s github.com -w)
[ -n "$TOKEN" ] || { echo "没读到 token"; exit 1; }

CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $TOKEN" \
  https://api.github.com/user)
[ "$CODE" = "200" ] || { echo "token 无效（HTTP $CODE）"; exit 1; }
echo "    验证通过"

echo "==> 创建 release $TAG"
python3 - "$ROOT" <<'PY'
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
body = ("""## 小焕的小篆输入法 v1.0.0

macOS 小篆输入法，两条路子：

- **拼音输入**：敲 `shui` → 候选窗以篆形显示「水 说 税 睡 谁」→ 上屏真小篆字符
- **部件反查**：敲 `水工` → 反查得「江」（输出真篆形，不做字形合成）

另含 **《说文》540 部检索**（按原书部序查某部所辖全部字）。

### 安装

1. 下载下方 `%s` 解压
2. 运行 `./install.sh`
3. 系统设置 → 键盘 → 文字输入 → 输入法 → 编辑，添加「小焕的小篆输入法」

### 验收

`python3 tools/acceptance.py` —— 35 项端到端检查，全部通过。
""" % "xiaohuan-xiaozhuan-ime-macOS-v1.0.0.zip")
json.dump({"tag_name": "v1.0.0", "target_commitish": "main",
           "name": "v1.0.0 — 首个可用版本", "body": body},
          open(root / "build" / "rel.json", "w", encoding="utf-8"),
          ensure_ascii=False)
PY
mkdir -p "$ROOT/build"
RID=$(curl -s -X POST -H "Authorization: token $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/releases" -d @"$ROOT/build/rel.json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id') or '')")
[ -n "$RID" ] || { echo "创建 release 失败（可能已存在，试试手动删除后重跑）"; exit 1; }
echo "    release id = $RID"

echo "==> 上传分发包"
curl -s -X POST -H "Authorization: token $TOKEN" -H "Content-Type: application/zip" \
  --data-binary @"$ASSET" \
  "https://uploads.github.com/repos/$REPO/releases/$RID/assets?name=$ASSET_NAME" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('    ->', d.get('browser_download_url') or d)"

echo
echo "完成：https://github.com/$REPO/releases/tag/$TAG"
