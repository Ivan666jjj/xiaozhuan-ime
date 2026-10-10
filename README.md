# 小焕的小篆输入法

macOS 上的小篆输入法，走两条路子：

| 路子 | 怎么用 | 例子 |
|---|---|---|
| **拼音输入** | 敲拼音，候选窗以篆形显示 | `shui` → 水 说 税 睡 谁 |
| **部件反查** | 敲部件，反查以这些部件构成的字 | `水工` → 江　`日木` → 杲/杳/果 |

```
拼音 "shui"  ──►  候选窗（水 说 税 睡 …，以篆形显示）  ──►  上屏 U+3EF5E 等小篆字符
部件 "水工"  ──►  反查得「江」  ──►  上屏「江」的真篆形
```

## 它能做什么

- 输入**无声调拼音**（`shui`、`lv`＝`lü`），实时给出候选，按「有篆形优先 + 常用度」排序
- 上屏的是**真正的小篆字符**（Unicode 18.0 小篆区块 `U+3D000–U+3FC3F`），
  在装了本字体的机器上可复制、可编辑、可再排版
- 简体字自动经「简 → 繁」规范化后再查篆形（`说→說`、`为→爲`、`国→國` …）
- **部件反查**：用部件拼键来找字，输出永远是查得到的真篆形（不做字形合成，原因见
  [`compose/README.md`](compose/README.md)）
- **《说文》540 部检索**：按原书部序查某部所辖全部字

## 安装

```bash
# 从源码构建（本项目内）
./build.sh install          # 编译 + 装输入法 + 装字体
./build.sh package          # 生成 dist/小焕的小篆输入法-macOS.zip

# 或直接用分发包
unzip 小焕的小篆输入法-macOS.zip && cd 小焕的小篆输入法 && ./install.sh
```

装完到 **系统设置 → 键盘 → 文字输入 → 输入法 → 编辑**，添加「小焕的小篆输入法」。

## 验收

```bash
python3 tools/acceptance.py   # 35 项端到端检查
python3 tools/check.py        # 工程自检
```

## 架构

```
core/                     转换内核（纯 Python，可独立使用）
  seal_index.py           SealSources.txt → 现代汉字 ↔ 小篆码位
  pinyin_engine.py        拼音 → 汉字候选（pypinyin 单字字典 + 词频排序）
  freq.py                 字频代理（pypinyin 词组词典统计）
  zhuan.py                统一入口：拼音/汉字 → 小篆
tools/
  fetch_all.py            并发抓汉典《说文》小篆 SVG（主区 + 补区）
  export_dict.py          导出 ime/Resources/seal_dict.json
  check.py                工程自检
  acceptance.py           端到端验收测试
font/
  build_font.py           SVG → TrueType（U+3D000 主区 + PUA 补区）
ime/
  ShuowenIME/             InputMethodKit 输入法（Swift）
  Resources/              Info.plist、seal_dict.json
compose/                   **部件反查输入法**（敲「水工」出「江」）
  decompose.py            字 → 部件（偏旁归一、去笔画、独体返回空）
  build_index.py          建反查索引
  lookup.py               查询（精确 + 子集匹配）
  cli.py                  命令行入口
  ids.txt                 汉字部件拆解数据

  SPEC.md                 交给模型实现的规格
  README.md               为什么是「反查」而不是「合成」——务必一读
zhuan.py                  拼音转小篆的命令行入口
build.sh                  构建 / 安装 / 卸载
```

## 三个必须知道的坑

**1. Unicode 小篆区块并不完整。** Unicode 18.0 的 `kSEAL_MCJK` 有约 2,918 条把篆形
对应成了**扩展区古字**（例如「二」记作「𠄞」、「五」记作「𢀑」），导致「七」「二」
「五」「小」「之」这类常用字查不到码位。实测 5,195 个常用字里只有 2,211 个有
Unicode 码位。

> 解决：**补区**。这类字从汉典单独抓篆形，用确定性公式编码到 PUA 私有区：
> `PUA = 0xF0000 + (汉字码位 - 0x3400)`（可逆，不需要额外映射表）。
> 代价：**补区字符离开本字体不可移植**——复制到没装该字体的机器会显示成方块。

**2. 没有任何系统字体支持小篆码位。** 本机 659 个字体里只有 `LastResort.otf`
（豆腐块兜底）"碰得到" `U+3D000`。所以字体必须自带，且**必须装到
`~/Library/Fonts/`**——目标 App 是别的进程，只在本进程注册字体没用。

**3. 输入模式的声明方式很反直觉。** 让系统认这个输入法，踩了三层：

| 现象 | 原因 | 解法 |
|---|---|---|
| 系统完全扫不到 | bundle 用 `.inputmethod` 后缀 | 改 `.app`（与 QianwenIME/WeType 一致），**立即生效，不用重登** |
| 扫到了但 `TISTypeKeyboardInputMethodWithoutModes`，切不过去 | `tsInputModeListKey` 直接放在 Info.plist 顶层 | 必须包在 **`ComponentInputModeDict`** 里，且每个模式要有 **`TISInputSourceID`**，并用 `tsVisibleInputModeOrderedArrayKey` 列出顺序（照抄 `/System/Library/Input Methods/AinuIM.app`） |
| 候选/控制器找不到 | Swift 类没有 ObjC 运行时名 | `@objc(SealInputController)` —— Info.plist 的 `InputMethodServerControllerClass` 是由 ObjC runtime 按名字实例化的 |

另外 `CFBundlePackageType` 要写 `APPL`（不是 `IMK`），后台常驻用 `LSUIElement`
而不是 `LSBackgroundOnly`。

## 用法

```bash
# 1. 抓字形（增量可反复跑，约 3-5 分钟）
python3 tools/fetch_all.py --workers 8

# 2. 合成字体
python3 font/build_font.py

# 3. 导出拼音词典
python3 tools/export_dict.py

# 4. 构建 + 安装（同时把字体装到 ~/Library/Fonts/）
./build.sh install

# 5. 自检（关键指标一目了然）
python3 tools/check.py
```

装完后到 **系统设置 → 键盘 → 文字输入 → 输入法 → 编辑**，添加「小篆输入法」，
然后按 Ctrl+Space（或 Fn 键）切过去。

```bash
./build.sh build       # 只构建
./build.sh font        # 只装字体
./build.sh uninstall   # 卸载
```

## 打字方式

| 操作 | 效果 |
|---|---|
| 输入拼音 `shui` | 候选窗显示 `水 说 税 睡 谁 …`（以篆形显示） |
| `1` ~ `9` 或空格 | 选第 N 个候选并上屏小篆字符 |
| `-` / `=` | 上下翻页 |
| 回车 | 上屏拼音原文 |
| Esc | 清空 |

每个候选下方的小红字是它对应的现代汉字，方便对认。

## 命令行内核（不装输入法也能用）

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from core.zhuan import ZhuanEngine
eng = ZhuanEngine()
print(eng.candidates('shui')[:5])          # 拼音候选
print(eng.text_to_seal('流水说小'))         # 整段转小篆
"
```

## 字形来源与授权

字形抓自[汉典](https://www.zdic.net/)（`img.zdic.net/swxz/`，即《说文》小篆），
**仅供个人使用，请勿公开分发**。映射与字形结构参考 Unicode 18.0
[`SealSources.txt`](https://www.unicode.org/Public/18.0.0/ucd/SealSources.txt)。

若要可商用的替代方案，可考虑台湾「全字库说文解字」（6712 字，政府开放授权），
但其官网在中国大陆需代理访问。
