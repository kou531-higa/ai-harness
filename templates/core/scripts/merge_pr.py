#!/usr/bin/env python3
"""PR を確かめてからマージする（make merge PR=<番号> から呼ぶ。人が実行する）。

GitHub の無料プランの非公開リポジトリでは、必須チェックを GitHub に強制させられない。
その代わりに、ここで次をすべて確かめてから squash マージする。

- PR が開いていて、下書きでない
- 人の判断待ち（needs-decision）のラベルが付いていない
- 検査が1つ以上あり、すべて成功している（実行中・失敗があれば止める）
- main に追いついている（遅れていれば止める）
- 確かめたときから、新しいコミットが積まれていない（--match-head-commit）
この PR の枝に積んだ PR があれば、マージの前に行き先をこの PR の行き先に付け替える（枝を消すと閉じてしまうため）。

AI はこのスクリプトを実行しない（.claude/settings.json で禁止している）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

FIELDS = "state,isDraft,labels,mergeable,mergeStateStatus,headRefOid,title,headRefName,baseRefName"
OK_BUCKETS = {"pass", "skipping"}
BLOCK_LABELS = {"needs-decision"}


def gh(*args: str) -> subprocess.CompletedProcess:
    exe = os.environ.get("HARNESS_GH", "gh")  # テストで差し替える
    return subprocess.run([exe, *args], capture_output=True, text=True, check=False)


def problems(pr: dict, checks: List[dict]) -> List[str]:
    out = []
    if pr.get("state") != "OPEN":
        out.append(f"PR が開いていません（{pr.get('state')}）")
    if pr.get("isDraft"):
        out.append("下書きの PR です")
    labels = {x["name"] for x in pr.get("labels", [])}
    for name in sorted(labels & BLOCK_LABELS):
        out.append(f"ラベル {name} が付いています（人の判断待ち）")
    if pr.get("mergeStateStatus") == "BEHIND":
        out.append("main に遅れています（gh pr update-branch --rebase で追いつかせる）")
    if pr.get("mergeable") == "CONFLICTING":
        out.append("main と衝突しています")
    if not checks:
        out.append("検査が1つもありません")
    for c in checks:
        if c.get("bucket") not in OK_BUCKETS:
            out.append(f"検査 {c.get('name')} が {c.get('bucket') or c.get('state')} です")
    return out


def retarget_stacked(head: str, base: str) -> List[str]:
    """この PR の枝（head）を行き先にしている開いた PR の行き先を、base に付け替える。付け替えた番号を返す。"""
    if not head or not base:
        return []
    r = gh("pr", "list", "--base", head, "--state", "open", "--json", "number")
    stacked = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip().startswith("[") else []
    moved = []
    for item in stacked:
        n = str(item["number"])
        if gh("pr", "edit", n, "--base", base).returncode == 0:
            moved.append(n)
    return moved


def record(number: str) -> None:
    try:
        d = Path(".harness")
        d.mkdir(exist_ok=True)
        event = {"ts": datetime.now(timezone.utc).isoformat(), "event": "merge", "pr": int(number)}
        with (d / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PR を確かめてから squash マージする")
    parser.add_argument("number", help="PR の番号")
    parser.add_argument("--dry-run", action="store_true", help="確かめるだけで、マージしない")
    args = parser.parse_args(argv)
    if not args.number.isdigit():
        print("PR の番号を指定してください（例：make merge PR=12）", file=sys.stderr)
        return 2

    r = gh("pr", "view", args.number, "--json", FIELDS)
    if r.returncode != 0:
        print(f"PR を読めません：{r.stderr.strip()}", file=sys.stderr)
        return 2
    pr = json.loads(r.stdout)
    r = gh("pr", "checks", args.number, "--json", "name,state,bucket")
    checks = json.loads(r.stdout) if r.stdout.strip().startswith("[") else []

    found = problems(pr, checks)
    print(f"PR #{args.number} {pr.get('title', '')}")
    if found:
        print("マージしません：")
        for p in found:
            print(f"  - {p}")
        return 1
    print(f"検査 {len(checks)} 件がすべて成功")
    if args.dry_run:
        print("（試しに実行：マージしていません）")
        return 0
    for n in retarget_stacked(pr.get("headRefName", ""), pr.get("baseRefName", "")):
        print(f"積んだ PR #{n} の行き先を {pr.get('baseRefName')} に付け替えました")
    r = gh("pr", "merge", args.number, "--squash", "--delete-branch", "--match-head-commit", pr["headRefOid"])
    if r.returncode != 0:
        print(f"マージに失敗しました：{r.stderr.strip()}", file=sys.stderr)
        return 1
    record(args.number)
    print("マージしました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
