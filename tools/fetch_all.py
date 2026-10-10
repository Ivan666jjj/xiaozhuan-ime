#!/usr/bin/env python3
"""并发抓取汉典《说文》小篆字形（主区 + 补区）。

主区：Unicode 18.0 小篆区块有码位的字，存成 ``fonts/raw/{U+3Dxxx}.svg``。
补区：Unicode 没码位、但汉典有篆形的常用字，存成 ``fonts/pua/{PUA}.svg``
      （PUA = 0xF0000 + 汉字码位 - 0x3400）。

汉典图按现代汉字码位存放，带 Referer 反盗链。单线程约 5 字/秒，
这里用线程池并发（默认 8 路），实测稳定在 40+ 字/秒且未触发限流。

用法::

    python3 tools/fetch_all.py --limit 200      # 试抓
    python3 tools/fetch_all.py                 # 全量（增量，可反复跑）
    python3 tools/fetch_all.py --workers 4     # 保守并发
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.seal_index import SealIndex  # noqa: E402

PUA_BASE = 0xF0000
PUA_ORIGIN = 0x3400
URL = "https://img.zdic.net/swxz/%04X.svg"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Referer": "https://www.zdic.net/",
}

_lock = threading.Lock()


def collect_tasks(idx: SealIndex, resume: bool) -> list[tuple[int, Path]]:
    """返回 (汉字码位, 目标文件) 的任务列表。目标文件已存在时跳过。"""
    tasks: list[tuple[int, Path]] = []
    raw_dir = ROOT / "fonts" / "raw"
    pua_dir = ROOT / "fonts" / "pua"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pua_dir.mkdir(parents=True, exist_ok=True)

    # 主区
    for e in idx.entries:
        dest = raw_dir / f"{ord(e.char):04X}.svg"
        if resume and dest.is_file() and dest.stat().st_size > 100:
            continue
        tasks.append((ord(e.modern), dest))

    # 补区
    from pypinyin.phrases_dict import phrases_dict

    common: set[str] = set()
    for phrase in phrases_dict:
        for ch in phrase:
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                common.add(ch)
    for ch in sorted(common, key=ord):
        if idx.seal_of(ch) is not None:
            continue  # 主区已有
        cp = ord(ch)
        if not (PUA_ORIGIN <= cp <= 0x9FFF):
            continue
        dest = pua_dir / f"{PUA_BASE + (cp - PUA_ORIGIN):05X}.svg"
        if resume and dest.is_file() and dest.stat().st_size > 100:
            continue
        tasks.append((cp, dest))
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(description="并发抓取汉典小篆字形")
    ap.add_argument("--data", default=str(ROOT / "data" / "SealSources.txt"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    idx = SealIndex(args.data)
    tasks = collect_tasks(idx, resume=not args.no_resume)
    if args.limit:
        tasks = tasks[: args.limit]
    total = len(tasks)
    print(f"待抓 {total} 个字形，{args.workers} 路并发", flush=True)
    if not total:
        print("全部已就绪")
        return 0

    counter = {"ok": 0, "miss": 0, "err": 0}
    t0 = time.time()

    def worker(chunk: list[tuple[int, Path]]) -> None:
        sess = requests.Session()
        sess.headers.update(HEADERS)
        for cp, dest in chunk:
            got = False
            for attempt in range(args.retries + 1):
                try:
                    r = sess.get(URL % cp, timeout=20)
                    if r.status_code == 200 and r.content.lstrip()[:4] == b"<svg":
                        dest.write_bytes(r.content)
                        got = True
                    break  # 404 之类不必重试
                except requests.RequestException:
                    if attempt == args.retries:
                        with _lock:
                            counter["err"] += 1
                        continue
                    time.sleep(0.5)
            with _lock:
                counter["ok" if got else "miss"] += 1
                done = counter["ok"] + counter["miss"] + counter["err"]
                if done % 500 == 0:
                    el = time.time() - t0
                    print(
                        f"  [{done}/{total}] ok={counter['ok']} miss={counter['miss']} "
                        f"err={counter['err']} ({done/el:.1f}/s)",
                        flush=True,
                    )

    # 均分成 workers 份，顺序处理（前面是常用字/主区）
    chunks: list[list[tuple[int, Path]]] = [[] for _ in range(args.workers)]
    for i, task in enumerate(tasks):
        chunks[i % args.workers].append(task)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker, c) for c in chunks if c]
        for f in as_completed(futures):
            f.result()

    el = time.time() - t0
    print(
        f"\n完成：成功 {counter['ok']}，无篆形 {counter['miss']}，出错 {counter['err']}，"
        f"用时 {el/60:.1f} 分 ({total/el:.1f}/s)"
    )

    # 刷新补区映射表
    pua_dir = ROOT / "fonts" / "pua"
    mapping: dict[str, int] = {}
    for f in pua_dir.glob("*.svg"):
        try:
            pua = int(f.stem, 16)
        except ValueError:
            continue
        ch_cp = PUA_ORIGIN + (pua - PUA_BASE)
        mapping[chr(ch_cp)] = pua
    map_path = ROOT / "data" / "pua_map.json"
    map_path.write_text(
        json.dumps(mapping, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"补区映射表 -> {map_path}（{len(mapping)} 字）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
