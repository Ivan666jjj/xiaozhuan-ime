# LICENSE-NOTES —— 授权范围说明

> `LICENSE` 里的 MIT **只覆盖本项目的代码**。这份文件说明代码之外的部分。

## MIT 覆盖什么

- `ime/` —— Swift 写的 macOS 输入法
- `tools/`、`font/`、`core/`、`compose/` —— Python 工具与构建脚本
- `build.sh`、`zhuan.py` 等

## 字形不适用 MIT

篆形来自第三方，各自另有授权：

| 来源 | 授权 | 在字体里的占比 |
|---|---|---|
| **开元小篆** | SIL Open Font License 1.1 | ~87% |
| **台湾全字库说文解字** | 政府资料开放授权条款第 1 版 | ~13% |

发布分发包时**必须一并带上**这两份声明（OFL 与 OGDL 都要求署名）：

- `packaging/KaiyuanSeal-OFL.txt` —— OFL 全文
- `packaging/字形来源与授权.md` —— 逐条落实署名要求
- `THIRD_PARTY_NOTICES.md` —— 含 Unicode 数据文件（`SealSources.txt`）的授权

## ⚠️ 默认构建会带上汉典字形（只能自用）

`python3 font/build_font.py`（不带参数）会用到**汉典**（zdic.net）的补缺字形，
多出 1249 个字。而**汉典的授权仅到「个人使用」**，那种版本**不能对外分发**。

**对外分发请用**：

```bash
./build.sh publish
```

它会自动改用不含汉典的合规字体重建，再打 macOS + Rime 两个包。

等价的手工做法：

```bash
python3 font/build_font.py --no-zdic
```
