"""harness コマンド。

harness init [導入先] [--layers web,api] [--force] [--dry-run] [--no-git-hook]
harness upgrade [導入先] [--dry-run]
harness doctor [対象] [--repo OWNER/REPO] [--out FILE]
harness stats [対象] [--since 28] [--repo OWNER/REPO] [--out FILE]
harness labels [--repo OWNER/REPO] [--dry-run]
harness version
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, stats
from .doctor import diagnose, render
from .init import run_init
from .labels import gh_commands
from .upgrade import NEW_SUFFIX, run_upgrade

NEXT_STEPS = """
次にすること（人が行う）
  1. CLAUDE.md の「動かし方」を、このプロジェクトのコマンドに合わせる
  2. .github/workflows/pr-check.yml の check ジョブに、言語のセットアップを足す
  3. Makefile にマージの入口を足す：
       merge:
       \tpython3 scripts/merge_pr.py $(PR)
  4. harness labels で、AI が止まった理由のラベルを作る
"""


def _print_list(title: str, items: List[str]) -> None:
    if items:
        print(f"{title}（{len(items)}）")
        for item in items:
            print(f"  {item}")


def cmd_init(args: argparse.Namespace) -> int:
    layers = None if args.layers is None else [x.strip() for x in args.layers.split(",") if x.strip()]
    try:
        plan = run_init(
            Path(args.target), layers, force=args.force, dry_run=args.dry_run, git_hook=not args.no_git_hook
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"harness init: {e}", file=sys.stderr)
        return 2
    if args.dry_run:
        print("（試しに実行：ファイルは変えていません）")
    _print_list("作成", plan.created)
    _print_list("上書き", plan.overwritten)
    _print_list("既にあるので触っていない", plan.skipped)
    for note in plan.notes:
        print(f"- {note}")
    if plan.skipped and not args.force:
        print("既にあるファイルを入れ替えるときは --force（差分を見てから）")
    print(NEXT_STEPS)
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    try:
        plan = run_upgrade(Path(args.target), dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"harness upgrade: {e}", file=sys.stderr)
        return 2
    if args.dry_run:
        print("（試しに実行：ファイルは変えていません）")
    print(f"版：{plan.from_version} → {__version__}")
    _print_list("足した", plan.added)
    _print_list("新しいテンプレートに入れ替えた（入れたまま触っていなかった）", plan.updated)
    _print_list(
        f"人が直しているので上書きしていない（新しいテンプレートを {NEW_SUFFIX} に置いた。手で合わせて消す）",
        plan.conflicts,
    )
    _print_list("人が直したまま（テンプレートは前回の upgrade から変わっていない）", plan.kept)
    _print_list("人が消しているので戻していない", plan.deleted_by_user)
    _print_list("テンプレートから消えた（消すかは人が決める）", plan.gone_from_template)
    print(f"変わらない：{len(plan.current)}件")
    for note in plan.notes:
        print(f"- {note}")
    if plan.conflicts:
        print(f"手で合わせるもの：{len(plan.conflicts)}件。例：diff -u <ファイル> <ファイル>{NEW_SUFFIX}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.target)
    text = render(diagnose(root, repo=args.repo), root.resolve())
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"書きました：{args.out}")
    else:
        print(text, end="")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    root = Path(args.target)
    text = stats.render(stats.collect(root, since_days=args.since, repo=args.repo), root.resolve())
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"書きました：{args.out}")
    else:
        print(text, end="")
    return 0


def cmd_labels(args: argparse.Namespace) -> int:
    for cmd in gh_commands(args.repo or ""):
        if args.dry_run:
            print(shlex.join(cmd))
            continue
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"失敗：{cmd[3]}：{r.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"作成：{cmd[3]}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="harness", description="AIは作業し、人は判断する")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="テンプレートをリポジトリに入れる")
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--layers", help="入れる層（カンマ区切り）。省略するとディレクトリから決める")
    p.add_argument("--force", action="store_true", help="既にあるファイルも上書きする")
    p.add_argument("--dry-run", action="store_true", help="何が変わるかだけを出す")
    p.add_argument("--no-git-hook", action="store_true", help="pre-push フックを入れない")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser(
        "upgrade", help="入れたあとに更新されたテンプレートを取り込む（人が直したファイルは上書きしない）"
    )
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--dry-run", action="store_true", help="何が変わるかだけを出す")
    p.set_defaults(func=cmd_upgrade)

    p = sub.add_parser("doctor", help="リポジトリを DORA の AI の7つの能力で 0〜3点に診断する（根拠つき）")
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--repo", help="PR を読む OWNER/REPO。省略すると今のリポジトリ")
    p.add_argument("--out", help="Markdown を書くファイル。省略すると画面に出す")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("stats", help="届ける力（PR から数える DORA の代わりの値）とハーネスの指標を数える")
    p.add_argument("target", nargs="?", default=".")
    p.add_argument("--since", type=int, default=28, help="何日前から数えるか（既定 28日）")
    p.add_argument("--repo", help="OWNER/REPO。省略すると対象のリポジトリ")
    p.add_argument("--out", help="Markdown を書くファイル。省略すると画面に出す")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("labels", help="AI が止まった理由のラベルを GitHub に作る")
    p.add_argument("--repo", help="OWNER/REPO。省略すると今のリポジトリ")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_labels)

    p = sub.add_parser("version", help="版を出す")
    p.set_defaults(func=lambda _a: print(__version__) or 0)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
