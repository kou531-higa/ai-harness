"""harness stats：届ける力（DORA）とハーネスの指標を、GitHub と手元の記録から数える。

元データ（読むだけ）：
- gh pr list：作成・マージの日時、行数、ラベル、ブランチ名
- gh issue list：needs-decision と ai-stop:* のラベル、作成・クローズの日時
- .harness/events.jsonl：フックが止めた記録（手元だけ。gitignore）
数えられないもの（データがない）は「測れない」と書く。推測で埋めない。
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .doctor import GH, default_gh

PR_FIELDS = "number,createdAt,mergedAt,state,additions,deletions,labels,headRefName"
ISSUE_FIELDS = "number,createdAt,closedAt,state,labels"


def _t(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _labels(item: dict) -> List[str]:
    return [lb["name"] for lb in item.get("labels", [])]


def _median(xs: List[float]) -> Optional[float]:
    return statistics.median(xs) if xs else None


@dataclass
class Stats:
    since: datetime
    until: datetime
    merged: int = 0
    lead_hours: Optional[float] = None
    size_median: Optional[float] = None
    fix_ratio: Optional[float] = None
    ai_stops: Dict[str, int] = field(default_factory=dict)
    decisions_closed: int = 0
    decision_days: Optional[float] = None
    decisions_open: int = 0
    hook_stops: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def per_week(self) -> float:
        weeks = max((self.until - self.since).days / 7, 1 / 7)
        return self.merged / weeks


def collect(
    root: Path, since_days: int = 28, gh: GH = default_gh, repo: Optional[str] = None, now: Optional[datetime] = None
) -> Stats:
    root = root.resolve()
    until = now or datetime.now(timezone.utc)
    since = until - timedelta(days=since_days)
    st = Stats(since=since, until=until)
    r = ["-R", repo] if repo else []
    prs = gh(["pr", "list", *r, "--state", "all", "--limit", "500", "--json", PR_FIELDS], root)
    issues = gh(["issue", "list", *r, "--state", "all", "--limit", "500", "--json", ISSUE_FIELDS], root)
    if prs is None:
        st.notes.append("PR を読めなかった（gh がない・ログインしていない）。PR の指標は測れない")
        prs = []
    if issues is None:
        st.notes.append("Issue を読めなかった。判断待ちの指標は Issue の分を数えていない")
        issues = []

    merged = [p for p in prs if p.get("mergedAt") and since <= _t(p["mergedAt"]) <= until]  # type: ignore[operator]
    st.merged = len(merged)
    if merged:
        st.lead_hours = _median([(_t(p["mergedAt"]) - _t(p["createdAt"])).total_seconds() / 3600 for p in merged])  # type: ignore[operator]
        st.size_median = _median([p["additions"] + p["deletions"] for p in merged])
        st.fix_ratio = sum(1 for p in merged if p.get("headRefName", "").startswith("fix/")) / len(merged)

    stops: Counter = Counter()
    for it in [*prs, *issues]:
        created = _t(it["createdAt"])
        if created and since <= created <= until:
            for lb in _labels(it):
                if lb.startswith("ai-stop:"):
                    stops[lb.split(":", 1)[1]] += 1
    st.ai_stops = dict(stops.most_common())

    waits = []
    for it in [*issues, *prs]:
        if "needs-decision" not in _labels(it):
            continue
        closed = _t(it.get("closedAt") or it.get("mergedAt"))
        if closed and since <= closed <= until:
            waits.append((closed - _t(it["createdAt"])).total_seconds() / 86400)  # type: ignore[operator]
        elif it.get("state") == "OPEN":
            st.decisions_open += 1
    st.decisions_closed = len(waits)
    st.decision_days = _median(waits)

    ev = root / ".harness" / "events.jsonl"
    if ev.is_file():
        hooks: Counter = Counter()
        for line in ev.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _t(rec.get("ts"))
            if ts and since <= ts <= until and rec.get("decision") in ("block", "deny", "stop"):
                hooks[rec.get("hook", "?")] += 1
        st.hook_stops = dict(hooks.most_common())
    else:
        st.notes.append(".harness/events.jsonl がない（フックの記録は手元にだけある）。フックで止めた回数は測れない")
    return st


def _fmt(v: Optional[float], unit: str, digits: int = 1) -> str:
    return "測れない" if v is None else f"{v:.{digits}f}{unit}"


def render(st: Stats, root: Path) -> str:
    out = [f"# harness stats：{root.name}", "", f"期間：{st.since:%Y-%m-%d}〜{st.until:%Y-%m-%d}", ""]
    out += ["## 届ける力（DORA の指標の代わりに、PR から数える）", "", "| 指標 | 値 |", "|---|---|"]
    out += [
        f"| マージした PR（デプロイの回数の代わり） | {st.merged}件（週 {st.per_week:.1f}件） |",
        f"| PR のリードタイムの中央値（作成 → マージ） | {_fmt(st.lead_hours, '時間')} |",
        f"| PR の行数の中央値 | {_fmt(st.size_median, '行', 0)} |",
        f"| 修正の PR の割合（fix/ ブランチ。変更失敗率の代わり） | {'測れない' if st.fix_ratio is None else f'{st.fix_ratio:.0%}'} |",
    ]
    out += ["", "## ハーネスの指標", "", "| 指標 | 値 |", "|---|---|"]
    stops = "、".join(f"{k} {v}" for k, v in st.ai_stops.items()) or "0件"
    hooks = "、".join(f"{k} {v}" for k, v in st.hook_stops.items()) or (
        "0件" if not any("events" in n for n in st.notes) else "測れない"
    )
    out += [
        f"| AI が止まった理由（ai-stop のラベル） | {stops} |",
        f"| 判断待ち：決まった件数と、決まるまでの日数の中央値 | {st.decisions_closed}件・{_fmt(st.decision_days, '日')} |",
        f"| 判断待ち：まだ決まっていない件数 | {st.decisions_open}件 |",
        f"| フックで止めた回数 | {hooks} |",
    ]
    if st.notes:
        out += ["", "## 測れなかったもの", ""] + [f"- {n}" for n in st.notes]
    out += ["", "デプロイの回数・変更失敗率・復旧時間は、本番のデータがないので PR から数えた代わりの値。"]
    return "\n".join(out) + "\n"
