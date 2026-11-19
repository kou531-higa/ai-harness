#!/usr/bin/env python3
"""AI レビューの割り振り（/review と PR の検査から使う）。

  python3 scripts/review_route.py --base origin/main            割り振りと未カバーを表で出す
  python3 scripts/review_route.py --base origin/main --json     /review が読む
  python3 scripts/review_route.py --base origin/main --strict   重要な所が未カバーなら exit 1

場所で選ぶ：変更したファイルのパスで担当を選ぶ（.claude/review-routes.json の paths）。
中身で足す：追加した行が content の正規表現に当たれば、その担当も足す（例：個人情報・状態名）。
未カバー：どの担当にも割り振られなかったファイル。critical に当たるものが未カバーなら、人に必ず示す。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

CONFIG = Path(".claude/review-routes.json")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def changed(base: str) -> Dict[str, List[str]]:
    """変更したファイルと、その追加行。消しただけのファイルも含める（追加行は空）。"""
    files: Dict[str, List[str]] = {p: [] for p in git("diff", "--name-only", f"{base}...HEAD").splitlines() if p}
    current = None
    for line in git("diff", "-U0", "--no-color", f"{base}...HEAD").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and current in files:
            files[current].append(line[1:])
    return files


def match(path: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def route(files: Dict[str, List[str]], config: dict) -> dict:
    assigned: Dict[str, Dict[str, List[str]]] = {}  # 担当 → ファイル → 理由
    for name, rule in config.get("reviewers", {}).items():
        regexes = [re.compile(r) for r in rule.get("content", [])]
        for path, added in files.items():
            reasons = []
            if match(path, rule.get("paths", [])):
                reasons.append("場所")
            hits = sorted({rx.pattern for rx in regexes for line in added if rx.search(line)})
            if hits:
                reasons.append("中身")
            if reasons:
                assigned.setdefault(name, {})[path] = reasons
    covered = {p for per in assigned.values() for p in per}
    uncovered = sorted(p for p in files if p not in covered)
    critical = config.get("critical", [])
    return {
        "files": sorted(files),
        "reviewers": {name: sorted(per) for name, per in assigned.items()},
        "reasons": {name: per for name, per in assigned.items()},
        "uncovered": uncovered,
        "critical_uncovered": [p for p in uncovered if match(p, critical)],
        "critical_changed": sorted(p for p in files if match(p, critical)),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AI レビューの担当を割り振る")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="重要な所が未カバーなら exit 1")
    args = parser.parse_args(argv)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    plan = route(changed(args.base), config)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(f"レビューの割り振り（{args.base} との差分、{len(plan['files'])}ファイル）\n")
        print("| 担当 | ファイル | 理由 |\n|---|---|---|")
        for name, per in plan["reasons"].items():
            for path, reasons in sorted(per.items()):
                print(f"| {name} | {path} | {'・'.join(reasons)} |")
        print(f"\n未カバー（どの担当も見ない）：{'、'.join(plan['uncovered']) or 'なし'}")
        print(f"重要な所で未カバー：{'、'.join(plan['critical_uncovered']) or 'なし'}")
        if plan["critical_changed"]:
            print(f"重要な所の変更（人も見る）：{'、'.join(plan['critical_changed'])}")
    if args.strict and plan["critical_uncovered"]:
        print("\n重要な所に担当がいません。.claude/review-routes.json に担当を足すか、人がレビューしてください。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
