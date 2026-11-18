#!/usr/bin/env python3
"""PreToolUse（Edit|Write）：編集してはいけないパスへの書き込みを止める。

ルールは .claude/hooks/protected-paths.txt に1行1パターンで書く。
  infra/envs/prod/**          このパターンに一致したら止める
  existing:api/migrations/**  git で管理済みのファイルだけ止める（新規作成は許す）
  # で始まる行はコメント
プロジェクトの外への書き込みも止める。
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as h  # noqa: E402

HOOK = "protect-paths"
RULES_FILE = ".claude/hooks/protected-paths.txt"


def load_rules(root: Path) -> List[Tuple[str, bool]]:
    """(パターン, 管理済みファイルだけか) の一覧を返す。"""
    path = root / RULES_FILE
    if not path.exists():
        return []
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        existing_only = line.startswith("existing:")
        pattern = line[len("existing:") :].strip() if existing_only else line
        rules.append((pattern, existing_only))
    return rules


def matches(rel: str, pattern: str) -> bool:
    # fnmatch の * は / にも一致するので、** は * と同じ扱いで足りる
    pat = pattern.replace("**", "*")
    if fnmatch.fnmatchcase(rel, pat):
        return True
    # "dir/" や "dir" はその下すべて
    base = pattern.rstrip("/*")
    return bool(base) and "*" not in base and (rel == base or rel.startswith(base + "/"))


def is_tracked(root: Path, rel: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel],
            cwd=str(root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return r.returncode == 0


def main() -> int:
    data = h.read_input()
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(file_path, str) or not file_path:
        return h.EXIT_OK

    root = h.project_dir(data)
    rel = h.relative_path(file_path, root)
    if rel is None:
        reason = f"プロジェクトの外への書き込みは禁止です: {file_path}"
        h.log_event(root, HOOK, "block", "outside-project", path=file_path)
        h.block(reason + "\n必要なら作業を止め、人に確認してください。")

    for pattern, existing_only in load_rules(root):
        if not matches(rel, pattern):
            continue
        if existing_only and not is_tracked(root, rel):
            continue
        kind = "管理済みのファイル" if existing_only else "パス"
        h.log_event(root, HOOK, "block", "protected-path", path=rel, pattern=pattern)
        h.block(
            f"このファイルは編集禁止です: {rel}\n"
            f"理由: 保護された{kind}（{RULES_FILE} の `{pattern}`）\n"
            "変更が必要なら、作業を止めて人へ戻してください（/decision-memo）。"
        )
    return h.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
