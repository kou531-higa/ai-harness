#!/usr/bin/env python3
"""PR の変更行数を検査する。上限を超えたら exit 1。

  python3 scripts/check_pr_size.py --base origin/main
  python3 scripts/check_pr_size.py --base origin/main --max 400 --labels "$LABELS"

- 数えるのは、追加行と削除行の合計
- ロックファイル・生成物（`*.generated.*`・`*_generated.py`）・バイナリは数えない（--exclude で追加できる）
- 人が `size-exception` ラベルを付けた PR は、上限を超えても通す（理由を PR に書く）
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from typing import List, Optional, Tuple

DEFAULT_MAX = 400
EXCEPTION_LABEL = "size-exception"
DEFAULT_EXCLUDES = [
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "*.min.js",
    "*.min.css",
    "*.snap",
    "*.svg",
    "docs/metrics/*",
    "*.generated.*",  # 生成物は、正本との食い違いを別の検査（make check など）で確かめる
    "*_generated.py",
]


def numstat(base: str) -> List[Tuple[int, int, str]]:
    out = subprocess.run(
        ["git", "diff", "--numstat", "--no-renames", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added == "-" or deleted == "-":  # バイナリ
            continue
        rows.append((int(added), int(deleted), path))
    return rows


def is_excluded(path: str, patterns: List[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(path, p) or fnmatch.fnmatchcase(name, p) for p in patterns)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PR の変更行数を検査する")
    parser.add_argument("--base", required=True, help="比べる先（例：origin/main）")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX)
    parser.add_argument("--labels", default="", help="PR のラベル（カンマ区切り）")
    parser.add_argument("--exclude", action="append", default=[], help="数えないパス（glob、複数可）")
    args = parser.parse_args(argv)

    patterns = DEFAULT_EXCLUDES + args.exclude
    rows = numstat(args.base)
    counted = [(a, d, p) for a, d, p in rows if not is_excluded(p, patterns)]
    total = sum(a + d for a, d, _ in counted)
    skipped = len(rows) - len(counted)

    print(f"変更行数: {total}（上限 {args.max}、数えなかったファイル {skipped}件）")
    if total <= args.max:
        return 0

    for a, d, p in sorted(counted, key=lambda r: -(r[0] + r[1]))[:10]:
        print(f"  {a + d:>5}  {p}")

    labels = {x.strip() for x in args.labels.split(",") if x.strip()}
    if EXCEPTION_LABEL in labels:
        print(f"\n上限を超えていますが、`{EXCEPTION_LABEL}` ラベルがあるので通します。理由を PR に書いてください。")
        return 0

    print(
        f"\n上限を超えています。PR を分けてください（1PR＝1チケット）。"
        f"\n分けられない理由があるときは、人が `{EXCEPTION_LABEL}` ラベルを付け、理由を PR に書きます。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
