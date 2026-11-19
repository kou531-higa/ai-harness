#!/usr/bin/env python3
"""未決事項台帳（docs/decisions/undecided.md）を、仕様から作る。

  python scripts/undecided_ledger.py            台帳を書き直す
  python scripts/undecided_ledger.py --check    台帳が仕様と合っていなければ exit 1（CI で使う）

台帳に載せるもの：仕様の未確定の印（check_undecided.py）と、仕様どうしの食い違い（check_spec_consistency.py）。
決定者は、仕様の frontmatter の owner、なければ決定者マップ（docs/decisions/owners.md）から選ぶ。
台帳は手で直さない。決まったら仕様を直し、台帳を作り直す。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_spec_consistency as consistency  # noqa: E402
import check_undecided as undecided  # noqa: E402

LEDGER = Path("docs/decisions/undecided.md")
OWNERS = Path("docs/decisions/owners.md")
TICKET_RE = re.compile(r"decision:\s*#(\d+)")


def read_owners(path: Path) -> Dict[str, str]:
    owners: Dict[str, str] = {}
    if not path.exists():
        return owners
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and line.startswith("|") and not set(cells[0]) <= {"-"} and cells[0] != "判断の種類":
            owners[cells[0]] = cells[1]
    return owners


def _id(*parts: str) -> str:
    return "U-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:6]


def _cell(text: str) -> str:
    return text.replace("|", "／").strip()


def rows(specs: Path, owners: Dict[str, str]) -> List[List[str]]:
    out = []
    for spec in undecided.find_specs(specs):
        report = undecided.analyze(spec)
        meta = undecided.parse_frontmatter(spec.read_text(encoding="utf-8").splitlines())
        owner = meta.get("owner", "").strip("'\"") or owners.get("仕様の未確定", "未定")
        for m in report.markers:
            text = m.text.lstrip("-* ").strip()
            ticket = TICKET_RE.search(m.text)
            where = f"{spec.as_posix()}:{m.line_no}"
            row = [
                _id("未確定", report.spec_id, text),
                f"未確定（{m.kind}）",
                report.spec_id,
                where,
                _cell(text),
                owner,
            ]
            out.append(row + [f"#{ticket.group(1)}" if ticket else "未起票"])
    findings = consistency.check(specs) if (specs / "functions.md").exists() else []  # 機能一覧がなければ突き合わせない
    for f in findings:
        owner = owners.get("仕様の食い違い", "未定")
        row = [_id("食い違い", f.kind, f.detail), f"食い違い（{f.kind}）", "-", f.where, _cell(f.detail), owner]
        out.append(row + ["未起票"])
    return out


def render(specs: Path, owners_path: Path) -> str:
    table = rows(specs, read_owners(owners_path))
    n_marker = sum(1 for r in table if r[1].startswith("未確定"))
    lines = [
        "# 未決事項台帳",
        "",
        "`python3 scripts/undecided_ledger.py` で仕様から作る。**手で直さない。** 決まったら仕様を直し、作り直す。",
        "",
        f"未確定 {n_marker}件・食い違い {len(table) - n_marker}件（元：`{specs.as_posix()}`）",
        "",
        "| ID | 種類 | 仕様 | 場所 | 内容 | 決定者 | 判断チケット |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in table]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="未決事項台帳を仕様から作る")
    parser.add_argument("--specs", default="docs/specs")
    parser.add_argument("--out", default=str(LEDGER))
    parser.add_argument("--owners", default=str(OWNERS))
    parser.add_argument("--check", action="store_true", help="台帳が古ければ exit 1")
    args = parser.parse_args(argv)

    text = render(Path(args.specs), Path(args.owners))
    out = Path(args.out)
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            print(
                f"未決事項台帳が仕様と合っていません。python3 scripts/undecided_ledger.py で作り直してください（{out}）"
            )
            return 1
        print("未決事項台帳は仕様と合っています")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"未決事項台帳を書きました：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
