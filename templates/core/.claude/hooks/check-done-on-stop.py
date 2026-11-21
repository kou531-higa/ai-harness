#!/usr/bin/env python3
"""Stop：変更があるのに検査が通っていなければ、終わらせない（完了の条件）。

既定では何もしない。使うときは環境変数で決める（settings.local.json の "env" か、claude -p を呼ぶ台本で）。
  HARNESS_STOP_CHECK=1                 有効にする
  HARNESS_STOP_CHECK_CMD="make check"  走らせる検査（既定は make check）
  HARNESS_STOP_CHECK_TIMEOUT=600       秒。超えたら通っていない扱い

- 変更：作業中のファイル（未追跡も含む。.gitignore・.harness/・__pycache__ は除く）が、
  既定の枝（origin/main、なければ main）と違う
- 同じ中身で一度通ったら、その記録（.harness/stop-check.json）があるうちは走らせ直さない
- stop_hook_active が true（すでに1回止めた後）なら止めない（終わらない輪にしないため）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True  # __pycache__ を作ると、それも変更に見えるため
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as h  # noqa: E402

HOOK = "check-done-on-stop"
RECORD = ".harness/stop-check.json"
BASES = ["origin/HEAD", "origin/main", "main"]
TAIL = 40


def git(root: Path, *args: str, env: Optional[dict] = None) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=False, env=env)
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def worktree_tree(root: Path) -> Optional[str]:
    """作業中のファイルを、仮の索引に入れて木の ID にする（本物の索引は触らない）。"""
    index = git(root, "rev-parse", "--git-path", "index")
    if index is None:
        return None
    index_path = Path(index) if Path(index).is_absolute() else root / index
    with tempfile.TemporaryDirectory() as tmp:
        tmp_index = Path(tmp) / "index"
        if index_path.exists():
            shutil.copy(str(index_path), str(tmp_index))
        env = dict(os.environ, GIT_INDEX_FILE=str(tmp_index))
        if git(root, "add", "-A", "--", ".", ":(exclude).harness", ":(exclude,glob)**/__pycache__/**", env=env) is None:
            return None
        return git(root, "write-tree", env=env)


def base_tree(root: Path) -> Optional[str]:
    for ref in BASES:
        tree = git(root, "rev-parse", "--verify", "-q", ref + "^{tree}")
        if tree:
            return tree
    return git(root, "rev-parse", "--verify", "-q", "HEAD^{tree}")


def read_record(root: Path) -> dict:
    try:
        data = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_record(root: Path, record: dict) -> None:
    try:
        (root / ".harness").mkdir(exist_ok=True)
        (root / RECORD).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    data = h.read_input()
    if os.environ.get("HARNESS_STOP_CHECK", "") not in ("1", "true", "yes"):
        return h.EXIT_OK
    if data.get("stop_hook_active"):
        return h.EXIT_OK

    root = h.project_dir(data)
    tree = worktree_tree(root)
    if tree is None or tree == base_tree(root):
        return h.EXIT_OK  # git でない、または変更がない

    cmd = os.environ.get("HARNESS_STOP_CHECK_CMD", "") or "make check"
    if read_record(root).get("tree") == tree and read_record(root).get("cmd") == cmd:
        return h.EXIT_OK

    try:
        timeout = int(os.environ.get("HARNESS_STOP_CHECK_TIMEOUT", "") or 600)
    except ValueError:
        timeout = 600
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        h.log_event(root, HOOK, "block", "timeout", cmd=cmd)
        h.block(f"検査（{cmd}）が時間切れです（{timeout}秒）。通っていない扱いにします。")
    if r.returncode == 0:
        write_record(root, {"tree": tree, "cmd": cmd})
        return h.EXIT_OK

    tail = "\n".join((r.stdout + r.stderr).rstrip().splitlines()[-TAIL:])
    h.log_event(root, HOOK, "block", "check-failed", cmd=cmd, code=r.returncode)
    h.block(
        f"変更がありますが、検査（{cmd}）が通っていません（終了コード {r.returncode}）。\n"
        f"{tail}\n\n直して検査を通してから終えてください。直せないときは、理由と出力を報告に書いてください。"
    )
    return h.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
