#!/usr/bin/env python3
"""Stop：変更した仕様に未確定が残っていて、判断チケットへのリンクがなければ終わらせない。

未確定の行に `decision: #123` があれば、判断メモを起票済みとみなす。
stop_hook_active が true（すでに1回止めた後）なら止めない。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as h  # noqa: E402

HOOK = "check-specs-on-stop"
SPECS_DIR = "docs/specs"
CHECKER = "scripts/check_undecided.py"


def changed_specs(root: Path) -> List[str]:
    """HEAD からの変更と未追跡のファイルのうち、仕様のもの。"""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", SPECS_DIR],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    paths = []
    for line in r.stdout.splitlines():
        if len(line) < 4 or line[:2].strip() == "D":
            continue
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        name = Path(path).name
        if path.endswith(".md") and not name.startswith("_"):
            paths.append(path)
    return paths


def load_checker(root: Path):
    path = root / CHECKER
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("check_undecided", str(path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_undecided"] = module  # dataclass が参照するため
    spec.loader.exec_module(module)
    return module


def main() -> int:
    data = h.read_input()
    if data.get("stop_hook_active"):
        return h.EXIT_OK

    root = h.project_dir(data)
    specs = changed_specs(root)
    if not specs:
        return h.EXIT_OK
    checker = load_checker(root)
    if checker is None:
        return h.EXIT_OK

    unlinked = []
    for rel in specs:
        report = checker.analyze(root / rel)
        for m in report.markers:
            if not m.linked:
                where = m.ac_id or f"{m.line_no}行目"
                unlinked.append(f"- {report.spec_id} {where}: {m.text}")

    if unlinked:
        h.log_event(root, HOOK, "block", "spec-undecided", count=len(unlinked))
        h.block(
            "変更した仕様に、判断メモのない未確定が残っています。\n"
            + "\n".join(unlinked)
            + "\n\n推測で埋めないでください。/decision-memo で1件ずつ判断チケットを起票し、"
            "未確定の行に `decision: #番号` を書いてから終えてください。"
        )
    return h.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
