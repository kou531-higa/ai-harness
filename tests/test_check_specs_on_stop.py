from __future__ import annotations

HOOK = "check-specs-on-stop.py"
STOP = {"hook_event_name": "Stop", "stop_hook_active": False}

SPEC_TBD = """---
id: SPEC-001
status: draft
---
## 合格基準
- AC-001-2 Given 受注101件 When 一覧を開く Then 1ページに TBD 件
"""

SPEC_LINKED = SPEC_TBD.replace("TBD 件", "TBD 件（decision: #12）")


def test_未確定が残っていれば終わらせない(project):
    project.write("docs/specs/SPEC-001.md", SPEC_TBD)
    r = project.run_hook(HOOK, STOP)
    assert r.returncode == 2
    assert "SPEC-001 AC-001-2" in r.stderr
    assert "/decision-memo" in r.stderr
    assert project.events()[-1]["reason"] == "spec-undecided"


def test_判断チケットにリンクしていれば通す(project):
    project.write("docs/specs/SPEC-001.md", SPEC_LINKED)
    r = project.run_hook(HOOK, STOP)
    assert r.returncode == 0, r.stderr


def test_2回目は止めない(project):
    project.write("docs/specs/SPEC-001.md", SPEC_TBD)
    r = project.run_hook(HOOK, {"hook_event_name": "Stop", "stop_hook_active": True})
    assert r.returncode == 0


def test_変更していない仕様は見ない(project):
    project.write("docs/specs/SPEC-001.md", SPEC_TBD)
    project.commit_all()
    r = project.run_hook(HOOK, STOP)
    assert r.returncode == 0


def test_コミット済みの仕様を変更したら見る(project):
    project.write("docs/specs/SPEC-001.md", SPEC_LINKED)
    project.commit_all()
    project.write("docs/specs/SPEC-001.md", SPEC_TBD)
    r = project.run_hook(HOOK, STOP)
    assert r.returncode == 2


def test_テンプレートは見ない(project):
    project.write("docs/specs/_template.md", SPEC_TBD)
    r = project.run_hook(HOOK, STOP)
    assert r.returncode == 0


def test_仕様以外の変更では何もしない(project):
    project.write("api/app/x.py", "# TBD\n")
    r = project.run_hook(HOOK, STOP)
    assert r.returncode == 0
