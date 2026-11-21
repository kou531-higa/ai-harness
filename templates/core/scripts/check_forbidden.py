#!/usr/bin/env python3
"""禁止パターンの検査（.claude/forbidden-patterns.json）。

  python3 scripts/check_forbidden.py --base origin/main   PR で追加した行だけを見る。当たれば exit 1
  python3 scripts/check_forbidden.py --all                管理しているファイルすべて（毎晩の一覧。今ある所を数える）
  --head <コミット>  HEAD の代わりに、そのコミットを見る（pre-push が push するコミットを渡す）

決まりの種類：
  pattern      正規表現に当たる行
  state-list   states に並べた状態名のうち、2つ以上を文字列で書いた行（「取り消せる注文か」などの判定の直書き）
例外：行末に「forbidden-ok: <id> <理由>」。理由のないものは例外にしない。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CONFIG = Path(".claude/forbidden-patterns.json")
OK_RE = re.compile(r"forbidden-ok:\s*([\w-]+)\s+\S")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def added_lines(base: str, head: str = "HEAD") -> List[Tuple[str, int, str]]:
    out, path, line_no = [], None, 0
    for line in git("diff", "-U0", "--no-color", f"{base}...{head}").splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            out.append((path, line_no, line[1:]))
            line_no += 1
    return out


def all_lines(head: Optional[str] = None) -> List[Tuple[str, int, str]]:
    """head がなければ作業中のファイル、あればそのコミットのファイル。"""
    out = []
    paths = git("ls-tree", "-r", "--name-only", head).splitlines() if head else git("ls-files").splitlines()
    for path in paths:
        try:
            if head:
                raw = subprocess.run(["git", "show", f"{head}:{path}"], capture_output=True, check=True).stdout
                text = raw.decode("utf-8")
            else:
                text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, subprocess.CalledProcessError):
            continue
        out += [(path, i + 1, line) for i, line in enumerate(text.splitlines())]
    return out


def compile_rules(config: dict) -> List[dict]:
    states = config.get("states", [])
    state_re = re.compile(r"['\"](" + "|".join(map(re.escape, states)) + r")['\"]") if states else None
    rules = []
    for r in config.get("rules", []):
        if r.get("kind") == "state-list":
            if state_re is None:
                continue  # 状態の一覧がなければ使わない
            rules.append({**r, "test": lambda line, rx=state_re: len(set(rx.findall(line))) >= 2})
        else:
            rx = re.compile(r["pattern"])
            rules.append({**r, "test": lambda line, rx=rx: bool(rx.search(line))})
    return rules


def in_scope(path: str, rule: dict) -> bool:
    def m(ps: List[str]) -> bool:
        return any(fnmatch.fnmatch(path, p) for p in ps)

    return m(rule.get("paths", ["*"])) and not m(rule.get("allow", []))


def check(lines: List[Tuple[str, int, str]], rules: List[dict]) -> List[Dict[str, object]]:
    found = []
    for path, no, text in lines:
        ok = {m.group(1) for m in OK_RE.finditer(text)}
        for r in rules:
            if r["id"] not in ok and in_scope(path, r) and r["test"](text):
                found.append(
                    {"rule": r["id"], "file": path, "line": no, "text": text.strip()[:160], "message": r["message"]}
                )
    return found


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="禁止パターンの検査")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--all", action="store_true", help="差分ではなく、管理しているファイルすべて")
    parser.add_argument("--head", default=None, help="見るコミット（既定は HEAD。--all では作業中のファイル）")
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rules = compile_rules(json.loads(Path(args.config).read_text(encoding="utf-8")))
    lines = all_lines(args.head) if args.all else added_lines(args.base, args.head or "HEAD")
    found = check(lines, rules)
    if args.json:
        print(json.dumps({"count": len(found), "items": found}, ensure_ascii=False, indent=2))
        return 1 if found else 0
    scope = "すべてのファイル" if args.all else f"{args.base} から追加した行"
    print(f"禁止パターン（{scope}）：{len(found)}件")
    for f in found:
        print(f"  [{f['rule']}] {f['file']}:{f['line']}  {f['text']}")
        print(f"      → {f['message']}")
    if found and not args.all:
        print("\n直すか、例外なら行末に「forbidden-ok: <id> <理由>」と書いて人に認めてもらってください。")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
