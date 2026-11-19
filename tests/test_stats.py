import json
from datetime import datetime, timezone
from pathlib import Path

from ai_harness import stats

NOW = datetime(2026, 11, 30, tzinfo=timezone.utc)
PRS = [
    {"number": 1, "createdAt": "2026-11-10T00:00:00Z", "mergedAt": "2026-11-11T00:00:00Z", "state": "MERGED",
     "additions": 100, "deletions": 0, "labels": [], "headRefName": "feat/1-a"},
    {"number": 2, "createdAt": "2026-11-12T00:00:00Z", "mergedAt": "2026-11-12T12:00:00Z", "state": "MERGED",
     "additions": 300, "deletions": 0, "labels": [{"name": "ai-stop:spec-undecided"}], "headRefName": "fix/2-b"},
    {"number": 3, "createdAt": "2026-11-20T00:00:00Z", "mergedAt": None, "state": "OPEN",
     "additions": 50, "deletions": 0, "labels": [{"name": "needs-decision"}, {"name": "ai-stop:security"}], "headRefName": "feat/3"},
    {"number": 4, "createdAt": "2026-09-01T00:00:00Z", "mergedAt": "2026-09-02T00:00:00Z", "state": "MERGED",
     "additions": 9999, "deletions": 0, "labels": [{"name": "ai-stop:other"}], "headRefName": "feat/old"},
]  # fmt: skip
ISSUES = [
    {"number": 7, "createdAt": "2026-11-16T00:00:00Z", "closedAt": "2026-11-18T00:00:00Z", "state": "CLOSED",
     "labels": [{"name": "needs-decision"}, {"name": "ai-stop:spec-undecided"}]},
]  # fmt: skip


def fake(args, _cwd):
    return PRS if args[0] == "pr" else ISSUES


def test_期間の中のPRと判断待ちを数える(tmp_path: Path):
    st = stats.collect(tmp_path, since_days=28, gh=fake, now=NOW)
    assert st.merged == 2  # 9月の PR は期間の外
    assert st.lead_hours == 18.0  # 24時間と12時間の中央値
    assert st.size_median == 200
    assert st.fix_ratio == 0.5
    assert st.ai_stops == {"spec-undecided": 2, "security": 1}
    assert (st.decisions_closed, st.decision_days, st.decisions_open) == (1, 2.0, 1)


def test_フックの記録を数え_なければ測れないと書く(tmp_path: Path):
    st = stats.collect(tmp_path, gh=fake, now=NOW)
    assert any("events.jsonl がない" in n for n in st.notes)
    assert "フックで止めた回数 | 測れない" in stats.render(st, tmp_path)
    (tmp_path / ".harness").mkdir()
    recs = [{"ts": "2026-11-20T00:00:00+00:00", "hook": "protect-paths", "decision": "block", "reason": "x"},
            {"ts": "2026-11-21T00:00:00+00:00", "hook": "protect-paths", "decision": "block", "reason": "x"},
            {"ts": "2026-01-01T00:00:00+00:00", "hook": "format-and-lint", "decision": "block", "reason": "x"}]  # fmt: skip
    (tmp_path / ".harness" / "events.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\nこわれた行\n", encoding="utf-8"
    )
    st = stats.collect(tmp_path, gh=fake, now=NOW)
    assert st.hook_stops == {"protect-paths": 2}


def test_週ごとの推移とダッシュボード(tmp_path: Path):
    st = stats.collect(tmp_path, since_days=28, gh=fake, now=NOW)
    by_week = {w: (m, s) for w, m, s in st.weekly}
    assert by_week["2026-11-09"] == (2, 1)  # 11-09（月）の週：マージ2件、ai-stop の付いた PR #2
    assert by_week["2026-11-16"] == (0, 2)  # 11-16（月）の週：Issue #7 と PR #3
    html = stats.render_html(st, tmp_path)
    assert "<svg" in html and "マージした PR" in html and "spec-undecided" in html
    empty = stats.collect(tmp_path, gh=lambda _a, _c: [], now=NOW)
    assert "この期間は、マージした PR も AI が止まった件数も 0件" in stats.render_html(empty, tmp_path)


def test_ghで読めなければ測れないと書く_推測で埋めない(tmp_path: Path):
    st = stats.collect(tmp_path, gh=lambda _a, _c: None, now=NOW)
    text = stats.render(st, tmp_path)
    assert st.merged == 0 and "PR を読めなかった" in text
    assert "PR のリードタイムの中央値（作成 → マージ） | 測れない" in text
