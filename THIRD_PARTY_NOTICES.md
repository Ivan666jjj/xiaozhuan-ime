# Third-party notices

This repository vendors the following third-party material. The code and
scripts of this project are licensed separately (see `LICENSE` and
`LICENSE-NOTES.md`); the notices below cover the vendored material only.

> **字体里的篆形不是本项目绘制的。** 字形轮廓（glyph outlines）来自下面三个来源，
> 各自的署名要求逐条落实如下。
> The seal-script glyph outlines in `ShuowenSeal.ttf` come from third parties.

## 字形来源一：开元小篆（Kaiyuan Small Seal Font）

- 来源：<https://github.com/frankslin/kaiyuan-small-seal-font>
- 授权：**SIL Open Font License 1.1**（全文见 `packaging/KaiyuanSeal-OFL.txt`）
- 许可：个人与企业均可免费使用（含商用），可自由传播、修改、制作衍生字体。
- 要求：① 保留版权声明与 OFL 全文；② 制作衍生字体时不得单独使用 "Kaiyuan"
  作为字体名。（本字体名为 `ShuowenSeal`，符合该要求。）
- 占比：本字体 11,081 个小篆区码位来自它。

## 字形来源二：臺灣「全字庫說文解字」TrueType 字型（CMEX 製作）

- 来源：全字库说文解字 TrueType 字型 <https://www.cns11643.gov.tw>
- 授权：**《政府資料開放授權條款 - 第 1 版》**（OGDL-Taiwan-1.0）
- 许可：不限时间及地域，可重制、编辑、公开传输或作其他利用（含商业利用），无须费用。
- **显名义务（OGDL 强制条款）**：公开发行、展示或利用本字体所产生的加值产品时，
  应以适当方式注明来源。OGDL 明定「未尽显名标示义务者，视为自始未取得开放资料之授权」。
  官方标示格式：

  > 數位發展部，CNS11643中文標準交換碼全字庫網站，https://www.cns11643.gov.tw

## 字形来源三：汉典（zdic.net）—— 仅限自用版，**不随分发包**

- 来源：<https://www.zdic.net>
- 授权：**仅限个人使用**，不得再分发。
- 因此 `build.sh publish`（即 `build_font.py --no-zdic`）构建的**分发包里不含任何汉典字形**。
- 若用 `build_font.py` 默认参数自行构建含汉典补缺的版本，那个版本**只能自用**。

## Unicode Character Database (`third_party/unicode/ucd/`)

`SealSources.txt` from Unicode 18.0.0 is used under the Unicode License v3
(SPDX identifier `Unicode-3.0`). The full license text is in
`third_party/unicode/ucd/LICENSE.txt`, and provenance is documented in
`third_party/unicode/ucd/README.md`.

> Copyright © 1991-2023 Unicode, Inc.
>
> Permission is hereby granted, free of charge, to any person obtaining a
> copy of data files and any associated documentation (the "Data Files") or
> software and any associated documentation (the "Software") to deal in the
> Data Files or Software without restriction, including without limitation
> the rights to use, copy, modify, merge, publish, distribute, and/or sell
> copies of the Data Files or Software, and to permit persons to whom the
> Data Files or Software are furnished to do so, provided that either (a)
> this copyright and permission notice appear with all copies of the Data
> Files or Software, or (b) this copyright and permission notice appear in
> associated Documentation.
>
> THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
> KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
> MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF
> THIRD PARTY RIGHTS.
>
> IN NO EVENT SHALL THE COPYRIGHT HOLDER OR HOLDERS INCLUDED IN THIS NOTICE
> BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL INDIRECT OR CONSEQUENTIAL DAMAGES,
> OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
> WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
> ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THE DATA
> FILES OR SOFTWARE.
>
> Except as contained in this notice, the name of a copyright holder shall
> not be used in advertising or otherwise to promote the sale, use or other
> dealings in these Data Files or Software without prior written
> authorization of the copyright holder.

Release archives of the fonts must include this notice.
