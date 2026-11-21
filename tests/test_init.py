"""harness init のテスト。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_harness.cli import main
from ai_harness.init import run_init


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)


@pytest.fixture
def target(tmp_path: Path) -> Path:
    for d in ("web", "api", "batch"):
        (tmp_path / d).mkdir()
    git_init(tmp_path)
    return tmp_path


def test_テンプレートとある層だけを入れる(target):
    plan = run_init(target)
    assert (target / "CLAUDE.md").exists()
    assert (target / ".claude/settings.json").exists()
    assert (target / ".claude/skills/feature/SKILL.md").exists()
    assert (target / "scripts/check_undecided.py").exists()
    assert (target / "api/CLAUDE.md").exists()
    assert not (target / "db/CLAUDE.md").exists()
    assert "web/CLAUDE.md" in plan.created
    manifest = json.loads((target / ".claude/harness.json").read_text(encoding="utf-8"))
    assert manifest["layers"] == ["web", "api", "batch"]


def test_キャッシュのファイルは入れない(target):
    plan = run_init(target)
    assert not [p for p in plan.created if "__pycache__" in p or p.endswith(".pyc")]


def test_既にあるファイルは上書きしない(target):
    (target / "CLAUDE.md").write_text("# 自分たちの規約\n", encoding="utf-8")
    plan = run_init(target)
    assert "CLAUDE.md" in plan.skipped
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "# 自分たちの規約\n"


def test_forceのときは上書きする(target):
    (target / "CLAUDE.md").write_text("# 古い\n", encoding="utf-8")
    plan = run_init(target, force=True)
    assert "CLAUDE.md" in plan.overwritten
    assert "古い" not in (target / "CLAUDE.md").read_text(encoding="utf-8")


def test_dry_runは何も変えない(target):
    plan = run_init(target, dry_run=True)
    assert plan.created
    assert not (target / "CLAUDE.md").exists()
    assert not (target / ".gitignore").exists()


def test_gitignoreには足りない行だけを足す(target):
    (target / ".gitignore").write_text("node_modules/\n.harness/\n", encoding="utf-8")
    run_init(target)
    run_init(target)  # 2回目は何も足さない
    lines = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".harness/") == 1
    assert lines.count("CLAUDE.local.md") == 1
    assert "node_modules/" in lines


def test_層を指定できる(target):
    run_init(target, layers=["api"])
    assert (target / "api/CLAUDE.md").exists()
    assert not (target / "web/CLAUDE.md").exists()


def test_知らない層は止める(target, capsys):
    assert main(["init", str(target), "--layers", "mobile"]) == 2
    assert "知らない層" in capsys.readouterr().err


def test_CLIは次にすることを出す(target, capsys):
    assert main(["init", str(target)]) == 0
    out = capsys.readouterr().out
    assert "次にすること" in out
    assert "make merge" not in out or "merge_pr.py" in out


def test_labelsは10の理由と判断待ちを作る(capsys):
    assert main(["labels", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("ai-stop:") == 10
    assert "needs-decision" in out
    assert "owner-approved" in out and "owner-digest" in out
    assert "--force" in out


def test_prepushフックを入れる(target):
    run_init(target)
    hook = target / ".git/hooks/pre-push"
    assert hook.exists()
    assert hook.stat().st_mode & 0o100


def test_既にあるprepushフックは残す(target):
    hook = target / ".git/hooks/pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    plan = run_init(target)
    assert "mine" in hook.read_text(encoding="utf-8")
    assert any("既にある" in n for n in plan.notes)
