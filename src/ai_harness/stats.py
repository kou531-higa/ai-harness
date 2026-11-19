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
from typing import Dict, List, Optional, Tuple

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
    weekly: List[Tuple[str, int, int]] = field(default_factory=list)  # (週の初め, マージした PR, AI が止まった件数)
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

    # 週ごとの推移（月曜はじまり）
    def week(d: datetime) -> str:
        return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")

    weeks: Dict[str, List[int]] = {}
    d = since
    while d <= until:
        weeks.setdefault(week(d), [0, 0])
        d += timedelta(days=7)
    weeks.setdefault(week(until), [0, 0])
    for p in merged:
        weeks.setdefault(week(_t(p["mergedAt"])), [0, 0])[0] += 1  # type: ignore[arg-type]
    for it in [*prs, *issues]:
        created = _t(it["createdAt"])
        if created and since <= created <= until and any(lb.startswith("ai-stop:") for lb in _labels(it)):
            weeks.setdefault(week(created), [0, 0])[1] += 1
    st.weekly = [(k, v[0], v[1]) for k, v in sorted(weeks.items())]

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


CSS = """
:root{--bg:#fff;--fg:#1d2433;--mut:#5b6475;--line:#d9dee7;--card:#f5f7fa;--a:#2f6fd0;--b:#c2410c}
@media (prefers-color-scheme:dark){:root{--bg:#12161d;--fg:#e6e9ef;--mut:#9aa3b2;--line:#2c3340;--card:#1a1f28;--a:#7fb0ff;--b:#fb923c}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0}h2{font-size:17px;margin:28px 0 8px}
.mut{color:var(--mut);font-size:13px}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border-radius:8px;padding:12px}.tile b{display:block;font-size:26px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600}svg text{fill:var(--mut);font-size:11px}.wrap{overflow-x:auto}
"""


def _chart(weekly: List[Tuple[str, int, int]]) -> str:
    """週ごとの棒（マージした PR と、AI が止まった件数）。数は棒の上にも書く"""
    if not weekly:
        return '<p class="mut">データがない</p>'
    if all(m == 0 and s == 0 for _, m, s in weekly):
        return '<p class="mut">この期間は、マージした PR も AI が止まった件数も 0件</p>'
    top = max(1, *(max(m, s) for _, m, s in weekly))
    w, h, pad = 64, 140, 20
    bars = []
    for i, (wk, m, s) in enumerate(weekly):
        x = 40 + i * w
        for j, (v, color) in enumerate(((m, "var(--a)"), (s, "var(--b)"))):
            bh = (h - pad) * v / top
            bx = x + j * 22
            bars.append(
                f'<rect x="{bx}" y="{h - bh}" width="18" height="{bh}" fill="{color}" rx="2"><title>{wk} {v}</title></rect>'
            )
            bars.append(f'<text x="{bx + 9}" y="{h - bh - 4}" text-anchor="middle">{v}</text>')
        bars.append(f'<text x="{x + 20}" y="{h + 16}" text-anchor="middle">{wk[5:]}</text>')
    width = 40 + len(weekly) * w
    legend = '<p class="mut"><span style="color:var(--a)">■</span> マージした PR　<span style="color:var(--b)">■</span> AI が止まった件数（ai-stop）。週は月曜はじまり</p>'
    return f'<div class="wrap"><svg width="{width}" height="{h + 24}" role="img" aria-label="週ごとの推移">{"".join(bars)}</svg></div>{legend}'


def render_html(st: Stats, root: Path) -> str:
    from html import escape

    def tile(label: str, value: str, note: str = "") -> str:
        return f'<div class="tile"><span class="mut">{escape(label)}</span><b>{escape(value)}</b><span class="mut">{escape(note)}</span></div>'

    rows = (
        "".join(f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in st.ai_stops.items())
        or '<tr><td colspan="2" class="mut">0件</td></tr>'
    )
    hooks = "".join(f"<tr><td>{escape(k)}</td><td>{v}</td></tr>" for k, v in st.hook_stops.items())
    hooks_html = (
        f"<table><tr><th>フック</th><th>止めた回数</th></tr>{hooks}</table>"
        if hooks
        else '<p class="mut">記録がない（測れない）</p>'
    )
    notes = "".join(f"<li>{escape(n)}</li>" for n in st.notes)
    body = f"""<h1>ハーネスの指標：{escape(root.name)}</h1>
<p class="mut">{st.since:%Y-%m-%d}〜{st.until:%Y-%m-%d}。GitHub の PR・Issue と、手元のフックの記録から数えた。推測で埋めない。</p>
<div class="tiles">{tile("マージした PR", f"{st.merged}件", f"週 {st.per_week:.1f}件")}{tile("リードタイムの中央値", _fmt(st.lead_hours, "時間"), "作成 → マージ")}{tile("PR の行数の中央値", _fmt(st.size_median, "行", 0))}{tile("判断待ち", f"{st.decisions_open}件", "まだ決まっていない")}</div>
<h2>週ごとの推移</h2>{_chart(st.weekly)}
<h2>AI が止まった理由</h2><table><tr><th>理由</th><th>件数</th></tr>{rows}</table>
<h2>判断待ちが決まるまで</h2><p>決まった {st.decisions_closed}件・中央値 {escape(_fmt(st.decision_days, "日"))}</p>
<h2>フックで止めた回数</h2>{hooks_html}
{f"<h2>測れなかったもの</h2><ul>{notes}</ul>" if notes else ""}
<p class="mut">デプロイの回数・変更失敗率は、本番のデータがないので PR から数えた代わりの値（修正の PR の割合 {"測れない" if st.fix_ratio is None else f"{st.fix_ratio:.0%}"}）。</p>"""
    return f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ハーネスの指標</title><style>{CSS}</style></head><body><main>{body}</main></body></html>\n'
