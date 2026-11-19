#!/usr/bin/env python3
"""PostToolUse（Edit|Write）：編集したファイルに整形と Lint をかける。

自動で直せない指摘が残ったら終了コード 2 で AI に返し、直させる。
ツールが入っていない場合は、その拡張子を飛ばす（止めない）。

ツールは、編集したファイルに一番近い層のものを使う（モノレポで web/・api/・batch/ が別々の設定を持つため）。
ファイルのあるディレクトリからリポジトリ直下まで順に上り、node_modules/.bin と .venv/bin を探す。
見つかった層のディレクトリで実行し、その層の設定（.eslintrc や pyproject.toml）が効くようにする。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hooklib as h  # noqa: E402

HOOK = "format-and-lint"
MAX_OUTPUT = 4000

# 拡張子 → (実行ファイル, [整形・自動修正のコマンド], [検査のコマンド])
# {file} は編集したファイルに置き換わる
Step = Tuple[str, List[List[str]], List[List[str]]]
STEPS: Dict[str, List[Step]] = {
    ".py": [
        ("ruff", [["ruff", "format", "{file}"], ["ruff", "check", "--fix", "{file}"]], [["ruff", "check", "{file}"]]),
    ],
    ".ts": [
        ("prettier", [["prettier", "--write", "{file}"]], []),
        ("eslint", [["eslint", "--fix", "{file}"]], [["eslint", "{file}"]]),
    ],
    ".sql": [
        ("sqlfluff", [["sqlfluff", "fix", "{file}"]], [["sqlfluff", "lint", "{file}"]]),
    ],
    ".tf": [
        ("terraform", [["terraform", "fmt", "{file}"]], []),
    ],
}
for ext in (".tsx", ".js", ".jsx", ".mjs"):
    STEPS[ext] = STEPS[".ts"]


def find_tool(root: Path, rel: str, name: str) -> Tuple[Optional[str], Path]:
    """(実行ファイル, 実行するディレクトリ) を返す。見つからなければ (None, root)。"""
    d = (root / rel).parent
    while True:
        for sub in (("node_modules", ".bin"), (".venv", "bin")):
            cand = d.joinpath(*sub, name)
            if cand.exists():
                return str(cand), d
        if d == root or root not in d.parents:
            break
        d = d.parent
    found = shutil.which(name)
    return found, root


def run(cmd: List[str], root: Path) -> Tuple[int, str]:
    r = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, check=False)
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    data = h.read_input()
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return h.EXIT_OK

    root = h.project_dir(data)
    rel = h.relative_path(file_path, root)
    if rel is None or not (root / rel).exists():
        return h.EXIT_OK

    steps = STEPS.get(Path(rel).suffix.lower(), [])
    problems = []
    for tool, fixers, checkers in steps:
        exe, cwd = find_tool(root, rel, tool)
        if exe is None:
            continue
        target = (root / rel).relative_to(cwd).as_posix()
        for cmd in fixers:
            run([exe] + [a.replace("{file}", target) for a in cmd[1:]], cwd)
        for cmd in checkers:
            code, out = run([exe] + [a.replace("{file}", target) for a in cmd[1:]], cwd)
            if code != 0:
                where = cwd.relative_to(root).as_posix() or "."
                command = " ".join(cmd[1:]).replace("{file}", target)
                problems.append(f"$ {tool} {command}  （{where} で実行）\n{out}")

    if problems:
        h.log_event(root, HOOK, "block", "lint", path=rel)
        text = "\n\n".join(problems)
        if len(text) > MAX_OUTPUT:
            text = text[:MAX_OUTPUT] + "\n…（以下省略）"
        h.block(f"自動で直せない指摘が残っています: {rel}\n\n{text}\n\n指摘を直してください。")
    return h.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
