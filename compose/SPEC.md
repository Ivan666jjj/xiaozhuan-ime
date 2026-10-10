# 任务：实现「小篆部件输入法」的 Python 核心模块

## 背景

我们有《说文》540 部的小篆字形，以及一套汉字部件拆解数据（IDS）。
目标：让用户**输入部件序列**（如「水工」）来**反查**以这些部件构成的小篆字，
输出该字**真实的篆形字符**（不合成字形）。

## 输入数据（已就位，不要修改）

1. `compose/ids.txt` —— 制表符分隔三列，格式：
   ```
   U+6C34	水	水
   U+6C90	沐	⿰氵木
   U+660E	明	⿰日月
   ```
   第 1 列码位，第 2 列字符，第 3 列 IDS 序列。
   IDS 结构符在 U+2FF0–U+2FFF：`⿰`左右 `⿱`上下 `⿲`左中右 `⿳`上中下
   `⿴`全包围 `⿵`上三包 `⿶`下三包 `⿷`左三包 `⿸`左上包 `⿹`右上包
   `⿺`左下包 `⿻`重叠。
   IDS 里可能出现 `[]` 包裹标记和纯 ASCII 大写字母（G/T/K/V…）表示"无法拆解的部件位"，**这些必须丢弃**。

2. `data/seal_index.json` —— 有真篆形的字表：
   ```json
   {"chars": "水木火…", "count": 12836}
   ```
   （我稍后会生成这个文件；`chars` 是一个字符串，每个字符都是有篆形的字。）

3. `compose/radical_alias.json` —— 楷书偏旁 -> 正字 的映射：
   ```json
   {"氵": "水", "亻": "人", "扌": "手", "艹": "艸", "忄": "心", "刂": "刀"}
   ```

## 需要实现的模块

新建目录 `compose/`，实现以下文件。

### 1. `compose/decompose.py`

```python
def load_ids(path) -> dict[str, str]
    """读 ids.txt，返回 {汉字: IDS序列}。跳过注释行(#)和空行。"""

def flatten(seq: str) -> list[str]:
    """把 IDS 序列展平成部件列表。
    - 丢弃结构符(U+2FF0-U+2FFF)
    - 丢弃 '[' ']'
    - 丢弃纯 ASCII 字母
    - 非 ASCII 部件按 alias 表归一到正字(alias 通过参数传入或模块级加载)
    - 去重并保持首次出现顺序
    """

def parts_of(char: str, ids: dict[str, str], alias: dict[str,str]) -> list[str]:
    """返回该字的部件列表。字不在 ids 里、或 IDS 就是字本身(独体)，返回 []。"""
```

### 2. `compose/build_index.py`

```python
def build(ids_path, seal_chars: str, alias: dict) -> dict
    """建立反查索引并落盘 compose/index.json。

    只收录「有真篆形」的字(在 seal_chars 里)。
    每个字算出部件集合 key（部件按 Unicode 码位排序后拼接，去重）。
    返回结构：
    {
      "version": 1,
      "by_parts": { "木水": ["沐","朩"], ... },   # key -> [字...]
      "by_char":  { "沐": ["水","木"], ... },      # 字 -> 部件列表(供显示编码)
      "stats": {"chars": 10804, "keys": 9000}
    }
    """
```

### 3. `compose/lookup.py`

```python
def load(path) -> dict
    """读 index.json。"""

def search(query_parts: list[str], index, limit=30) -> list[dict]
    """核心查询。

    规则（重要，按此实现）：
    1. 把 query_parts 归一化(alias 映射、去重、按码位排序)得到 qkey。
    2. 精确匹配：index['by_parts'][qkey] 全部命中，排最前。
    3. 否则子集匹配：找出所有「部件集合 ⊇ qkey」的字，按 部件数从少到多 排序
       （部件越少说明匹配越紧凑），同数按码位。
    4. 返回 [{"char": 汉字, "parts": [...], "exact": True/False}]。
    """

def explain(char: str, index) -> str
    """返回该字的部件编码显示，如 '沐 = 水 + 木'。没有则返回 '<char> (独体/未收录)'。"""
```

### 4. `compose/cli.py`

命令行：
```
python3 compose/cli.py 水工            # 查询
python3 compose/cli.py --build         # 重建索引
python3 compose/cli.py --explain 沐    # 显示某字的部件
python3 compose/cli.py --json 水木     # JSON 输出
```
- 查询结果每行显示：`小篆字符  汉字  (部件码)`，并在末尾附上该字的**篆形字符**（从 seal 数据查）。
- 查不到时输出提示并返回码 1。

## 硬性要求

- Python 3.9+ 兼容（**不要用 3.10+ 的 match 语句，不要用 `X | Y` 类型注解**，用 `typing.Optional`/`Union`；用 `from __future__ import annotations` 也不要用新语法糖）。
- 只用标准库（不要 requests、不要第三方）。
- 全部函数带类型注解和中文 docstring。
- 出错给清晰中文信息，非零退出码。
- 不要打印调试信息到 stdout（用 stderr）。
- 代码用 `if __name__ == "__main__":` 保护。

## 交付

只输出**完整可运行的代码**，每个文件一个 ```python 代码块，并在每个代码块前用一行注明文件路径，如：
`### compose/lookup.py`

不要输出解释性文字。
