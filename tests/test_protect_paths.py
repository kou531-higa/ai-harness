from __future__ import annotations

import pytest

HOOK = "protect-paths.py"


def edit(path: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": path}}


@pytest.mark.parametrize(
    "path",
    [
        "infra/envs/prod/main.tf",
        "infra/envs/prod/modules/rds/variables.tf",
        ".env",
        ".env.production",
        ".github/workflows/pr-check.yml",
        ".claude/settings.json",
        ".claude/hooks/protect-paths.py",
    ],
)
def test_保護されたパスは止める(project, path):
    r = project.run_hook(HOOK, edit(str(project.path / path)))
    assert r.returncode == 2
    assert "編集禁止" in r.stderr
    assert project.events()[-1]["reason"] == "protected-path"


@pytest.mark.parametrize("path", ["api/app/main.py", "infra/envs/stg/main.tf", "docs/specs/SPEC-001.md", ".envrc"])
def test_それ以外は通す(project, path):
    r = project.run_hook(HOOK, edit(str(project.path / path)))
    assert r.returncode == 0, r.stderr


def test_相対パスでも判定する(project):
    r = project.run_hook(HOOK, edit("infra/envs/prod/main.tf"))
    assert r.returncode == 2


def test_パスの細工で抜けられない(project):
    r = project.run_hook(HOOK, edit(str(project.path / "infra/envs/stg/../prod/main.tf")))
    assert r.returncode == 2


def test_プロジェクトの外は止める(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "x.py"
    r = project.run_hook(HOOK, edit(str(outside)))
    assert r.returncode == 2
    assert "プロジェクトの外" in r.stderr


def test_適用済みのマイグレーションは止め_新規は通す(project):
    project.write("api/migrations/versions/0001_init.py", "# applied\n")
    project.commit_all()
    applied = project.run_hook(HOOK, edit(str(project.path / "api/migrations/versions/0001_init.py")))
    new = project.run_hook(HOOK, edit(str(project.path / "api/migrations/versions/0002_add.py")))
    assert applied.returncode == 2
    assert "管理済み" in applied.stderr
    assert new.returncode == 0, new.stderr


def test_file_pathがなければ何もしない(project):
    r = project.run_hook(HOOK, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert r.returncode == 0


def test_入力が壊れていても止まらない(project):
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, str(project.path / ".claude/hooks" / HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        cwd=project.path,
        check=False,
    )
    assert r.returncode == 0
