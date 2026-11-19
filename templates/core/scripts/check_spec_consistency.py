#!/usr/bin/env python3
"""仕様どうしの食い違いを検査する。機能一覧を基準に、画面仕様・遷移図・ユースケースを突き合わせる。

  python scripts/check_spec_consistency.py docs/specs          食い違いがあれば一覧を出して exit 1
  python scripts/check_spec_consistency.py docs/specs --json   一覧を JSON で出す（未決事項台帳に入れる）

読む文書（docs/specs の下）：
  functions.md        機能一覧。表の列「画面ID」「画面名」「表示件数」「遷移先」（遷移先は、で区切る）
  screens/*.md        画面仕様。frontmatter に id・page_size・transitions（, で区切る）
  transitions.md      遷移図。Mermaid の「SCR-001 --> SCR-002」の行
  usecases/*.md       ユースケース。frontmatter に screens（, で区切る）

見つけるもの：画面ID（ない・余分）／件数（表示件数のずれ）／遷移先（3つの文書のずれ）。
見つけて並べるまで。どちらを直すかは人が決める。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

ID_RE = re.compile(r"SCR-\d{3}")
EDGE_RE = re.compile(r"(SCR-\d{3})\s*-+>\s*(?:\|[^|]*\|\s*)?(SCR-\d{3})")


@dataclass
class Finding:
    kind: str  # 画面ID／件数／遷移先
    where: str
    detail: str


def split_ids(value: str) -> Set[str]:
    return set(ID_RE.findall(value or ""))


def frontmatter(path: Path) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta: Dict[str, str] = {}
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.split("#", 1)[0].strip().strip("'\"[]")
    return meta


def read_function_list(path: Path) -> Dict[str, Dict[str, str]]:
    """機能一覧の表を {画面ID: {列名: 値}} にする。"""
    rows: Dict[str, Dict[str, str]] = {}
    header: Optional[List[str]] = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue  # 区切りの行
        row = dict(zip(header, cells))
        ids = ID_RE.findall(row.get("画面ID", ""))
        if ids:
            rows[ids[0]] = row
    return rows


def check(specs: Path) -> List[Finding]:
    found: List[Finding] = []
    func_path = specs / "functions.md"
    if not func_path.exists():
        return [Finding("画面ID", str(func_path), "機能一覧がない")]
    funcs = read_function_list(func_path)

    screens: Dict[str, Dict[str, str]] = {}
    for p in sorted((specs / "screens").glob("*.md")):
        meta = frontmatter(p)
        sid = meta.get("id", "")
        if sid:
            screens[sid] = dict(meta, _path=str(p))

    # 画面ID
    for sid in sorted(set(funcs) - set(screens)):
        found.append(Finding("画面ID", str(func_path), f"{sid} は機能一覧にあるが、画面仕様がない"))
    for sid in sorted(set(screens) - set(funcs)):
        found.append(Finding("画面ID", screens[sid]["_path"], f"{sid} は画面仕様があるが、機能一覧にない"))

    # 件数
    for sid in sorted(set(funcs) & set(screens)):
        a, b = funcs[sid].get("表示件数", "").strip(), screens[sid].get("page_size", "").strip()
        if a and b and a != b:
            found.append(Finding("件数", screens[sid]["_path"], f"{sid} の表示件数：機能一覧は {a}、画面仕様は {b}"))

    # 遷移先
    diagram: Dict[str, Set[str]] = {}
    tpath = specs / "transitions.md"
    if tpath.exists():
        for src, dst in EDGE_RE.findall(tpath.read_text(encoding="utf-8")):
            diagram.setdefault(src, set()).add(dst)
    for sid in sorted(set(funcs) & set(screens)):
        f = split_ids(funcs[sid].get("遷移先", ""))
        s = split_ids(screens[sid].get("transitions", ""))
        d = diagram.get(sid, set()) if tpath.exists() else None
        sources = {"機能一覧": f, "画面仕様": s}
        if d is not None:
            sources["遷移図"] = d
        if len({frozenset(v) for v in sources.values()}) > 1:
            detail = "、".join(f"{k} {','.join(sorted(v)) or 'なし'}" for k, v in sources.items())
            found.append(Finding("遷移先", screens[sid]["_path"], f"{sid} の遷移先が食い違う：{detail}"))

    # ユースケースが参照する画面
    known = set(funcs) | set(screens)
    for p in sorted((specs / "usecases").glob("*.md")):
        for sid in sorted(split_ids(frontmatter(p).get("screens", "")) - known):
            found.append(Finding("画面ID", str(p), f"ユースケースが、存在しない画面 {sid} を参照している"))
    return found


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="仕様どうしの食い違いを検査する")
    parser.add_argument("specs", nargs="?", default="docs/specs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    found = check(Path(args.specs))
    if args.json:
        print(json.dumps({"count": len(found), "items": [asdict(f) for f in found]}, ensure_ascii=False, indent=2))
        return 0
    if not found:
        print("食い違い: 0件")
        return 0
    print(f"食い違い: {len(found)}件")
    for f in found:
        print(f"  [{f.kind}] {f.detail}  ({f.where})")
    print("\nどちらを直すかは人が決めます。重要なものは判断メモ（/decision-memo）にしてください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
