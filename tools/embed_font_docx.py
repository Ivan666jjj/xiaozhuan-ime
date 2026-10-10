#!/usr/bin/env python3
"""把 Shuowen Seal 字体嵌入 .docx —— 让对方不装字体也能看到篆形。

Word/WPS 打开文档时会读 ``word/fontTable.xml`` 里的 ``<w:embedRegular>``，
再从 ``word/fonts/*.odttf`` 加载字体，于是**没装字体的机器也能正常显示**。

odttf 的混淆算法（ECMA-376 Part 4「Font Embedding」）：
  1. 生成 GUID，存进 ``w:fontKey``
  2. 把 GUID 的 16 字节**反转**作为密钥
  3. 用密钥与前 32 字节 XOR（字节 0-15 对密钥 0-15，字节 16-31 再来一遍）

字体在嵌入前会做**子集化**（只留文档里用到的字形），否则 13 MB 全塞进文档。
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent

FONT_REL_ID = "rIdFontEmbed1"
ODTTF_PART = "word/fonts/font1.odttf"
ODTTF_CT = "application/vnd.openxmlformats-officedocument.obfuscatedFont"
REL_FONT_TYPE = ("http://schemas.openxmlformats.org/officeDocument/"
                 "2006/relationships/font")

FONT_TABLE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="{FONT_REL_ID}" Type="{REL_FONT_TYPE}" Target="fonts/font1.odttf"/>'
    "</Relationships>"
)


def obfuscate(data: bytes, font_key: str) -> bytes:
    """按 ECMA-376 把字体数据混淆成 .odttf（XOR 自逆，解回来用同一个函数）。"""
    key = bytes.fromhex(font_key.strip("{}").replace("-", ""))[::-1]  # 反转字节序
    out = bytearray(data)
    for i in range(min(32, len(out))):
        out[i] ^= key[i % 16]
    return bytes(out)


def subset_font(font_path: Path, text: str) -> bytes:
    """只保留 ``text`` 里出现的字形。name 表原样保留（Word 靠 family name 匹配）。"""
    opts = subset.Options()
    opts.text = text
    opts.drop_tables += ["DSIG"]
    opts.recalc_bounds = True
    opts.recalc_timestamp = False
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.layout_features = ["*"]
    font = subset.load_font(str(font_path), opts)
    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buf = BytesIO()
    subset.save_font(font, buf, opts)
    return buf.getvalue()


def _add_embed_regular(font_table: str, font_name: str, font_key: str) -> str:
    """在 <w:font w:name="..."> 里追加 <w:embedRegular>（CT_Font 里它排在最后）。"""
    embed = (f'<w:embedRegular r:id="{FONT_REL_ID}" '
             f'w:fontKey="{font_key}" w:subsetted="true"/>')
    pattern = re.compile(
        r'(<w:font\s+w:name="' + re.escape(font_name) + r'"[^>]*>)(.*?)(</w:font>)',
        re.S)
    new, n = pattern.subn(lambda m: m.group(1) + m.group(2) + embed + m.group(3),
                          font_table)
    if n:
        return new
    # 表里还没这个字体 —— 新建一条
    return font_table.replace(
        "</w:fonts>",
        f'<w:font w:name="{font_name}">{embed}</w:font></w:fonts>')


def _add_odttf_content_type(content_types: str) -> str:
    if "odttf" in content_types:
        return content_types
    # 必须插在 <Types …> 开标签**之后**。
    # 曾经写成 replace(">", …, 1)，结果替换的是 XML 声明末尾那个 ">"，
    # 把 <Default> 放到根元素前面 —— 包变成无效 XML，WPS 直接打不开。
    m = re.search(r"<Types\b[^>]*>", content_types)
    if not m:
        return content_types
    decl = f'<Default Extension="odttf" ContentType="{ODTTF_CT}"/>'
    return content_types[:m.end()] + decl + content_types[m.end():]


def _add_embed_flag(settings: str) -> str:
    """加 <w:embedTrueTypeFonts/>。CT_Settings 顺序要求它在 zoom 之后、proofState 之前。"""
    if "embedTrueTypeFonts" in settings:
        return settings
    flag = "<w:embedTrueTypeFonts/>"
    for anchor in ("<w:proofState", "<w:defaultTabStop", "<w:compat", "</w:settings>"):
        idx = settings.find(anchor)
        if idx != -1:
            return settings[:idx] + flag + settings[idx:]
    return settings


def embed(docx_in: Path, font_path: Path, font_name: str, out_path: Path) -> dict:
    with zipfile.ZipFile(docx_in) as z:
        items = {i.filename: z.read(i.filename) for i in z.infolist()}
        infos = {i.filename: i for i in z.infolist()}

    # 收集文档里真正用到的字符（含 fontTable / styles 等所有文本）
    used = set()
    for name, blob in items.items():
        if name.endswith(".xml"):
            try:
                used.update(blob.decode("utf-8"))
            except UnicodeDecodeError:
                pass
    used.discard("\n")
    used.discard("\r")
    text = "".join(sorted(c for c in used if c.isprintable()))

    font_bytes = font_path.read_bytes()
    subset_bytes = subset_font(font_path, text)
    font_key = "{" + str(uuid.uuid4()).upper() + "}"
    odttf = obfuscate(subset_bytes, font_key)

    # fontTable.xml 必须在
    if "word/fontTable.xml" not in items:
        items["word/fontTable.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            '<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "</w:fonts>").encode("utf-8")

    items["word/fontTable.xml"] = _add_embed_regular(
        items["word/fontTable.xml"].decode("utf-8"), font_name, font_key).encode("utf-8")
    items["word/_rels/fontTable.xml.rels"] = FONT_TABLE_RELS.encode("utf-8")
    items[ODTTF_PART] = odttf
    items["[Content_Types].xml"] = _add_odttf_content_type(
        items["[Content_Types].xml"].decode("utf-8")).encode("utf-8")
    if "word/settings.xml" in items:
        items["word/settings.xml"] = _add_embed_flag(
            items["word/settings.xml"].decode("utf-8")).encode("utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, blob in items.items():
            zout.writestr(infos.get(name, name), blob)

    return {
        "fontKey": font_key,
        "fontBytes": len(font_bytes),
        "subsetBytes": len(subset_bytes),
        "glyphsUsed": len(text),
        "docxBytes": out_path.stat().st_size,
    }


def verify(out_path: Path) -> list[str]:
    """复核：包结构合法、odttf 能解回有效字体、各部件与关系齐全。

    注意这里**必须真解析 XML** —— 早先只查了字符串出现与否，
    结果 `[Content_Types].xml` 把 <Default> 插到根元素前面（非法 XML）
    也没被发现，文档在 WPS 里直接打不开。
    """
    import xml.etree.ElementTree as ET

    from fontTools.ttLib import TTFont

    problems: list[str] = []
    with zipfile.ZipFile(out_path) as z:
        names = z.namelist()

        # OOXML 要求 [Content_Types].xml 是包里第一个条目
        if not names or names[0] != "[Content_Types].xml":
            problems.append(f"第一个条目应是 [Content_Types].xml，实际是 "
                            f"{names[0] if names else '(空包)'}")

        # 所有 XML / rels 部件都必须是合法 XML
        for name in names:
            if name.endswith((".xml", ".rels")):
                try:
                    ET.fromstring(z.read(name))
                except ET.ParseError as exc:
                    problems.append(f"{name} 不是合法 XML：{exc}")

        names = set(names)
        for need in (ODTTF_PART, "word/fontTable.xml",
                     "word/_rels/fontTable.xml.rels"):
            if need not in names:
                problems.append(f"缺少部件：{need}")
        if problems:
            return problems

        ft = z.read("word/fontTable.xml").decode("utf-8")
        m = re.search(r'<w:embedRegular[^>]*w:fontKey="(\{[^}]+\})"', ft)
        if not m:
            problems.append("fontTable.xml 里没有 embedRegular / fontKey")
            return problems
        key = m.group(1)

        odttf = z.read(ODTTF_PART)
        restored = obfuscate(odttf, key)          # XOR 自逆
        try:
            f = TTFont(BytesIO(restored), fontNumber=0)
            fam = [str(r) for r in f["name"].names if r.nameID == 1]
            if not fam:
                problems.append("还原出的字体没有 family name")
        except Exception as exc:
            problems.append(f"odttf 解不回有效字体：{exc}")

        if ODTTF_CT not in z.read("[Content_Types].xml").decode("utf-8"):
            problems.append("Content_Types 里缺 odttf 声明")
        if "embedTrueTypeFonts" not in z.read("word/settings.xml").decode("utf-8"):
            problems.append("settings.xml 里缺 embedTrueTypeFonts")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="把字体嵌入 .docx")
    ap.add_argument("docx", help="输入 .docx")
    ap.add_argument("--font", default=str(ROOT / "build" / "ShuowenSeal.ttf"))
    ap.add_argument("--font-name", default="Shuowen Seal")
    ap.add_argument("--out", help="输出 .docx（默认在原文件名后加 _嵌入字体）")
    args = ap.parse_args()

    src = Path(args.docx)
    if not src.is_file():
        print(f"找不到：{src}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else src.with_name(
        src.stem + "_嵌入字体" + src.suffix)

    stats = embed(src, Path(args.font), args.font_name, out)
    print(f"字体原始 {stats['fontBytes']/1024/1024:.1f} MB -> "
          f"子集 {stats['subsetBytes']/1024:.0f} KB（用到 {stats['glyphsUsed']} 个字符）")
    print(f"fontKey = {stats['fontKey']}")
    print(f"-> {out}（{stats['docxBytes']/1024/1024:.1f} MB）")

    problems = verify(out)
    if problems:
        print("\n复核发现问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("复核通过：odttf 可还原、部件与关系齐全")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
