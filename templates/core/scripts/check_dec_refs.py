#!/usr/bin/env python3
"""参照している DEC-番号の判断記録が、docs/decisions/ にあるかを確かめる。ないものがあれば exit 1。

  python3 scripts/check_dec_refs.py docs/specs                       仕様が参照する DEC
  python3 scripts/check_dec_refs.py --body-file pr.md docs/specs     PR の本文も見る
  echo "DEC-001 による" | python3 scripts/check_dec_refs.py -        標準入力を見る

- 判断記録は、ファイル名が `DEC-<番号>` で始まるもの、または frontmatter の `id: DEC-<番号>` で見つける
- 型（`_` で始まるファイル）と `DEC-000` は数えない
- 決定の正本は判断記録と仕様。チケットのコメントだけにある決定は、参照しても見つからない扱いになる
- PR の本文では、`…` とコードの囲み（```）の中の番号は例として数えない（例を書くときは囲む）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

DEC_RE = re.compile(r"\bDEC-(\d{3,})\b")
ID_RE = re.compile(r"^id:\s*['\"]?(DEC-\d{3,})", re.M)
DECISIONS = Path("docs/decisions")


def known_decisions(root: Path) -> Set[str]:
    found: Set[str] = set()
    if not root.is_dir():
        return found
    for p in root.rglob("*.md"):
        if p.name.startswith("_"):
            continue
        m = re.match(r"(DEC-\d{3,})", p.name)
        if m:
            found.add(m.group(1))
        try:
            head = p.read_text(encoding="utf-8")[:2000]
        except (OSError, UnicodeDecodeError):
            continue
        found |= set(ID_RE.findall(head))
    return found


CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def without_code(text: str) -> str:
    """コードの囲みと `…` を、改行だけ残して消す（行の番号は変えない）"""
    return CODE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def refs_in(text: str, where: str) -> List[Tuple[str, str]]:
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for num in DEC_RE.findall(line):
            if set(num) != {"0"}:
                out.append((f"DEC-{num}", f"{where}:{no}"))
    return out


def collect(paths: List[str], body_file: Optional[str]) -> List[Tuple[str, str]]:
    refs: List[Tuple[str, str]] = []
    if body_file:
        refs += refs_in(without_code(Path(body_file).read_text(encoding="utf-8")), "PR の本文")
    for arg in paths:
        if arg == "-":
            refs += refs_in(sys.stdin.read(), "標準入力")
            continue
        p = Path(arg)
        files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
        for f in files:
            if f.name.startswith("_") or not f.exists():
                continue
            try:
                refs += refs_in(f.read_text(encoding="utf-8"), f.as_posix())
            except (OSError, UnicodeDecodeError):
                continue
    return refs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="参照している DEC の判断記録があるかを確かめる")
    parser.add_argument("paths", nargs="*", help="見るファイルかディレクトリ（- で標準入力）")
    parser.add_argument("--body-file", help="PR の本文のファイル")
    parser.add_argument("--decisions", default=str(DECISIONS), help="判断記録の置き場所")
    args = parser.parse_args(argv)

    known = known_decisions(Path(args.decisions))
    missing: Dict[str, List[str]] = {}
    for dec, where in collect(args.paths, args.body_file):
        if dec not in known:
            missing.setdefault(dec, []).append(where)

    print(f"見つからない DEC：{len(missing)}件（判断記録 {len(known)}件）")
    for dec in sorted(missing):
        print(f"  {dec}  ← {'、'.join(missing[dec][:5])}")
    if missing:
        print(
            f"\n{args.decisions}/ に判断記録（_template.md の型）を書いてください。"
            "\nチケットのコメントにある決定は正本にしません。判断記録か仕様に書き戻してから参照します。"
        )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
