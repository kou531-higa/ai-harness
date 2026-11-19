#!/usr/bin/env python3
"""仕様（docs/specs/*.md）の未確定と書式を検査する。

  python scripts/check_undecided.py docs/specs                     一覧を出すだけ（exit 0）
  python scripts/check_undecided.py docs/specs --require approved  承認に必要な条件を満たさなければ exit 1
  python scripts/check_undecided.py docs/specs --json              一覧を JSON で出す（未決事項台帳に入れる）

未確定の印は5種類（プレイブック15枚目）：TBD／要確認・保留／TODO／確認待ち／書きかけ（ほかに 未定・???）。
「保留」は業務の状態の名前にも使われるので、【保留】（保留）[保留] 保留： のような印の書き方のときだけ拾う。

--require approved では、status が review か approved の仕様に対して次を求める。
  - 未確定の印が0件
  - 「## 対象外」の節がある
  - 「## 合格基準」の各項目に ID（AC-001-1）と Given／When／Then がある
コードブロックの中は対象外。ファイル名が _ で始まるもの（テンプレート）は飛ばす。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

MARKERS = [
    ("TBD", re.compile(r"\bTBD\b")),
    ("要確認", re.compile(r"要確認")),
    ("保留", re.compile(r"[【（(\[]保留[】）)\]]|保留[:：]")),
    ("TODO", re.compile(r"\bTODO\b")),
    ("確認待ち", re.compile(r"確認待ち")),
    ("書きかけ", re.compile(r"書きかけ")),
    ("未定", re.compile(r"未定")),
    ("???", re.compile(r"\?\?\?")),
]
DECISION_LINK_RE = re.compile(r"decision:\s*#\d+")
AC_ID_RE = re.compile(r"^AC-\d{3}-\d+\b")
STATUSES_REQUIRING_APPROVAL = {"review", "approved"}


@dataclass
class Marker:
    line_no: int
    text: str
    kind: str  # どの印か
    ac_id: Optional[str]
    linked: bool  # 判断チケット（decision: #NN）へのリンクがあるか


@dataclass
class SpecReport:
    path: Path
    spec_id: str
    status: str
    markers: List[Marker] = field(default_factory=list)
    format_errors: List[str] = field(default_factory=list)

    def errors_for_approval(self) -> List[str]:
        errs = [f"未確定 {m.ac_id or f'{m.line_no}行目'}: {m.text}" for m in self.markers]
        return errs + self.format_errors


def parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.split("#", 1)[0].strip().strip("'\"")
            meta[key.strip()] = value
    return meta


def body_lines(lines: List[str]) -> Iterable[tuple]:
    """(行番号, 行) を返す。frontmatter とコードブロックを除く。"""
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    in_code = False
    for i in range(start, len(lines)):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            yield i + 1, line


def analyze(path: Path) -> SpecReport:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta = parse_frontmatter(lines)
    report = SpecReport(path=path, spec_id=meta.get("id", path.stem), status=meta.get("status", ""))

    section = ""
    sections = set()
    current_ac: Optional[str] = None
    ac_items: List[tuple] = []  # (行番号, ID or None, 本文)

    for line_no, line in body_lines(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            sections.add(section)
            current_ac = None
            continue

        if section == "合格基準":
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                m = AC_ID_RE.match(item)
                current_ac = m.group(0) if m else None
                ac_items.append([line_no, current_ac, item])
            elif stripped and ac_items:
                ac_items[-1][2] += " " + stripped  # 継続行

        kind = next((k for k, rx in MARKERS if rx.search(line)), None)
        if kind:  # 1行に複数あっても1件と数える
            report.markers.append(
                Marker(
                    line_no=line_no,
                    text=stripped,
                    kind=kind,
                    ac_id=current_ac if section == "合格基準" else None,
                    linked=bool(DECISION_LINK_RE.search(line)),
                )
            )

    if "対象外" not in sections:
        report.format_errors.append("「## 対象外」の節がない")
    if "合格基準" not in sections:
        report.format_errors.append("「## 合格基準」の節がない")
    for line_no, ac_id, text in ac_items:
        if ac_id is None:
            report.format_errors.append(f"{line_no}行目: 合格基準に ID（AC-001-1 の形）がない")
            continue
        missing = [w for w in ("Given", "When", "Then") if w not in text]
        if missing:
            report.format_errors.append(f"{ac_id}: {'／'.join(missing)} がない")
    return report


def find_specs(target: Path) -> List[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.md") if not p.name.startswith("_"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="仕様の未確定と書式を検査する")
    parser.add_argument("paths", nargs="*", default=["docs/specs"])
    parser.add_argument("--require", choices=["approved"], help="承認に必要な条件を満たさなければ exit 1")
    parser.add_argument("--json", action="store_true", help="未確定の一覧を JSON で出す")
    args = parser.parse_args(argv)

    if args.json:
        items = []
        for target in args.paths:
            for spec in find_specs(Path(target)):
                r = analyze(spec)
                for m in r.markers:
                    items.append(
                        {
                            "file": str(spec),
                            "line": m.line_no,
                            "spec": r.spec_id,
                            "kind": m.kind,
                            "ac": m.ac_id,
                            "linked": m.linked,
                            "text": m.text,
                        }
                    )
        print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
        return 0

    failed = False
    for target in args.paths:
        for spec in find_specs(Path(target)):
            r = analyze(spec)
            needs = args.require == "approved" and r.status in STATUSES_REQUIRING_APPROVAL
            errs = r.errors_for_approval() if needs else []
            if needs and errs:
                failed = True
                print(f"{r.spec_id}（{r.status}）: {len(errs)}件  {spec}")
                for e in errs:
                    print(f"  - {e}")
            elif r.markers:
                print(f"{r.spec_id}（{r.status or 'status なし'}）: 未確定 {len(r.markers)}件  {spec}")
    if failed:
        print("\n未確定は推測で埋めず、判断メモ（/decision-memo）にしてください。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
