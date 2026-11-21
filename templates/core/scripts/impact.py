#!/usr/bin/env python3
"""影響範囲の候補を、層ごとに並べる（/impact から使う）。

  python3 scripts/impact.py ON_HOLD CANCELLED         言葉（状態名・テーブル名・関数名など）を含む所
  python3 scripts/impact.py ON_HOLD --json

git で管理しているファイルを、言葉そのもので探す（正規表現ではない）。
層（web・api・batch・db・e2e・docs・catalog）と種類（コード・テスト・仕様・SQL）に分け、
コードに当たるのにテストに当たらない層を「テストなし」として出す。
見つけるのは候補まで。本当に影響するかは、読んで確かめる。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, Optional

LAYERS = ["web", "api", "batch", "db", "e2e", "docs", "catalog"]
TEST_RE = re.compile(r"(\.spec\.|\.test\.|\.db-spec\.|(^|/)tests?/|(^|/)test_[^/]*\.py$|^e2e/)")
SKIP_RE = re.compile(
    r"(package-lock\.json|uv\.lock|\.lock$|\.(png|jpg|ico|svg|pdf|pptx)$|^docs/decisions/undecided\.md$)"
)
MAX_LINES = 3


def tracked_files() -> List[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p and not SKIP_RE.search(p)]


def layer_of(path: str) -> str:
    top = path.split("/", 1)[0]
    return top if top in LAYERS else "other"


def kind_of(path: str) -> str:
    if path.startswith(("docs/", "catalog/")) or path.endswith(".md"):
        return "仕様・文書"
    if TEST_RE.search(path):
        return "テスト"
    if path.endswith(".sql"):
        return "SQL"
    return "コード"


def search(terms: List[str], files: List[str]) -> List[dict]:
    hits = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        found = [(i + 1, line.strip()) for i, line in enumerate(lines) if any(t in line for t in terms)]
        if found:
            matched = sorted({t for t in terms if any(t in line for _, line in found)})
            hits.append(
                {
                    "file": path,
                    "layer": layer_of(path),
                    "kind": kind_of(path),
                    "terms": matched,
                    "count": len(found),
                    "lines": [{"line": n, "text": t[:160]} for n, t in found[:MAX_LINES]],
                }
            )
    return hits


def summarize(hits: List[dict]) -> Dict[str, Dict[str, int]]:
    table: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for h in hits:
        table[h["layer"]][h["kind"]] += 1
    return table


def untested_layers(table: Dict[str, Dict[str, int]]) -> List[str]:
    return [
        layer
        for layer in LAYERS + ["other"]
        if layer in table
        and (table[layer].get("コード", 0) + table[layer].get("SQL", 0))
        and not table[layer].get("テスト")
    ]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="影響範囲の候補を層ごとに並べる")
    parser.add_argument("terms", nargs="+", help="探す言葉（そのままの文字列）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    hits = search(args.terms, tracked_files())
    table = summarize(hits)
    untested = untested_layers(table)
    if args.json:
        print(
            json.dumps({"terms": args.terms, "hits": hits, "untested_layers": untested}, ensure_ascii=False, indent=2)
        )
        return 0

    print(f"言葉：{'・'.join(args.terms)}　当たったファイル：{len(hits)}件")
    print("\n| 層 | コード | SQL | テスト | 仕様・文書 |\n|---|---|---|---|---|")
    for layer in LAYERS + ["other"]:
        if layer in table:
            t = table[layer]
            counts = " | ".join(str(t.get(k, 0)) for k in ("コード", "SQL", "テスト", "仕様・文書"))
            print(f"| {layer} | {counts} |")
    for layer in LAYERS + ["other"]:
        group = [h for h in hits if h["layer"] == layer]
        if not group:
            continue
        print(f"\n## {layer}")
        for h in group:
            print(f"- {h['file']}（{h['kind']}・{h['count']}行）")
            for x in h["lines"]:
                print(f"    {x['line']}: {x['text']}")
    if untested:
        print(f"\nテストなし（コードに当たるのに、テストに当たらない層）：{'・'.join(untested)}")
        print("変える前に、今の振る舞いを固定するテストを書くか、未カバーとして人に伝える。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
