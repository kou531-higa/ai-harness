#!/usr/bin/env python3
"""PR の変更行数を、本体とテストに分けて検査する。どちらかが上限を超えたら exit 1。

  python3 scripts/check_pr_size.py --base origin/main
  python3 scripts/check_pr_size.py --base origin/main --max 400 --max-tests 800 --labels "$LABELS"

- 数えるのは、追加行と削除行の合計。本体（テストを除く）とテストを別に数える
- 上限の既定は、本体 400行・テスト 800行。--max・--max-tests か、
  環境変数 HARNESS_PR_MAX・HARNESS_PR_MAX_TESTS で変えられる
- ロックファイル・スナップショット・生成物（`*.generated.*`・`*_generated.py`）・バイナリは数えない
  （--exclude で追加できる）
- テストは、名前（`test_*`・`*.spec.*` など）か場所（`tests/`・`__tests__/`・`e2e/` など）で見分ける
- 人が `size-exception` ラベルを付けた PR は、上限を超えても通す（理由を PR に書く）
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from typing import List, Optional, Tuple

DEFAULT_MAX = 400
DEFAULT_MAX_TESTS = 800
EXCEPTION_LABEL = "size-exception"

# いつも数えないもの（テストの名前でも数えない）
ALWAYS_EXCLUDES = [
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "*.min.js",
    "*.min.css",
    "*.snap",
    "*/__snapshots__/*",
    "__snapshots__/*",
    "*.svg",
    "docs/metrics/*",
]
# 生成物。正本との食い違いは別の検査（make check など）で確かめる。テストは名前が生成物の形でも数える
GENERATED = ["*.generated.*", "*_generated.py"]
# 後方互換のため残す（ほかのスクリプトが読む）
DEFAULT_EXCLUDES = ALWAYS_EXCLUDES + GENERATED

TEST_NAMES = ["test_*", "*_test.py", "*_test.go", "*.spec.*", "*.test.*", "*.db-spec.*", "conftest.py"]
TEST_DIRS = {"tests", "test", "__tests__", "e2e", "spec"}


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


def _match(path: str, patterns: List[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(path, p) or fnmatch.fnmatchcase(name, p) for p in patterns)


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if any(fnmatch.fnmatchcase(name, t) for t in TEST_NAMES):
        return True
    return bool(set(path.split("/")[:-1]) & TEST_DIRS)


def is_excluded(path: str, patterns: List[str]) -> bool:
    """patterns は、いつも数えないもの（ALWAYS_EXCLUDES と --exclude）。生成物は別に見る。"""
    if _match(path, patterns):
        return True
    return _match(path, GENERATED) and not is_test(path)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PR の変更行数を、本体とテストに分けて検査する")
    parser.add_argument("--base", required=True, help="比べる先（例：origin/main）")
    parser.add_argument("--max", type=int, default=env_int("HARNESS_PR_MAX", DEFAULT_MAX), help="本体の上限")
    parser.add_argument(
        "--max-tests", type=int, default=env_int("HARNESS_PR_MAX_TESTS", DEFAULT_MAX_TESTS), help="テストの上限"
    )
    parser.add_argument("--labels", default="", help="PR のラベル（カンマ区切り）")
    parser.add_argument("--exclude", action="append", default=[], help="数えないパス（glob、複数可）")
    args = parser.parse_args(argv)

    patterns = ALWAYS_EXCLUDES + args.exclude
    rows = numstat(args.base)
    counted = [(a, d, p) for a, d, p in rows if not is_excluded(p, patterns)]
    body = [r for r in counted if not is_test(r[2])]
    tests = [r for r in counted if is_test(r[2])]
    body_total = sum(a + d for a, d, _ in body)
    test_total = sum(a + d for a, d, _ in tests)
    skipped = len(rows) - len(counted)

    print(
        f"変更行数: 本体 {body_total}行（上限 {args.max}）・テスト {test_total}行（上限 {args.max_tests}）"
        f"、数えなかったファイル {skipped}件"
    )
    over = []
    if body_total > args.max:
        over.append(("本体", body))
    if test_total > args.max_tests:
        over.append(("テスト", tests))
    if not over:
        return 0

    for kind, group in over:
        print(f"\n{kind}が上限を超えています。大きいファイル：")
        for a, d, p in sorted(group, key=lambda r: -(r[0] + r[1]))[:10]:
            print(f"  {a + d:>5}  {p}")

    labels = {x.strip() for x in args.labels.split(",") if x.strip()}
    if EXCEPTION_LABEL in labels:
        print(f"\n上限を超えていますが、`{EXCEPTION_LABEL}` ラベルがあるので通します。理由を PR に書いてください。")
        return 0

    print(
        f"\n上限を超えています。PR を分けてください（1PR＝1チケット。分けるときも、それぞれ main から作る）。"
        f"\n分けられない理由があるときは、人が `{EXCEPTION_LABEL}` ラベルを付け、理由を PR に書きます。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
