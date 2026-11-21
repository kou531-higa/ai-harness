"""pre-push フックを、本物の git の push で確かめる（相手の参照がないとき＝SHA が全部 0）。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "templates" / "core"

FORBIDDEN = {
    "states": [],
    "rules": [{"id": "no-debug", "pattern": "DEBUG_ONL[Y]", "message": "デバッグの印を残さない", "paths": ["*"]}],
}


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "test@example.com")
    git(work, "config", "user.name", "test")
    git(work, "remote", "add", "origin", str(remote))
    (work / "scripts").mkdir()
    shutil.copy(CORE / "scripts" / "check_forbidden.py", work / "scripts" / "check_forbidden.py")
    (work / ".claude").mkdir()
    (work / ".claude" / "forbidden-patterns.json").write_text(json.dumps(FORBIDDEN), encoding="utf-8")
    (work / "README.md").write_text("init\n", encoding="utf-8")
    hook = work / ".git" / "hooks" / "pre-push"
    shutil.copy(CORE / "scripts" / "git-hooks" / "pre-push", hook)
    hook.write_text(hook.read_text(encoding="utf-8").replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1))
    hook.chmod(0o755)
    return work


def commit(work: Path, rel: str, text: str) -> None:
    p = work / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(work, "add", "-A")
    assert git(work, "commit", "-q", "-m", f"add {rel}").returncode == 0


def test_空のリポジトリへの最初のmainのpushは通す(repo):
    commit(repo, "app.py", "x = 1\n")
    r = git(repo, "push", "-q", "origin", "main")
    assert r.returncode == 0, r.stderr


def test_空のリポジトリでも禁止パターンがあれば止める(repo):
    commit(repo, "app.py", "x = 1  # DEBUG_ONLY\n")
    r = git(repo, "push", "-q", "origin", "main")
    assert r.returncode != 0
    assert "禁止パターン" in r.stdout + r.stderr


def test_中身のあるリポジトリのmainへのpushは止める(repo):
    commit(repo, "app.py", "x = 1\n")
    assert git(repo, "push", "-q", "origin", "main").returncode == 0
    commit(repo, "app.py", "x = 2\n")
    r = git(repo, "push", "-q", "origin", "main")
    assert r.returncode != 0
    assert "make merge" in r.stderr


def test_新しいブランチは既定の枝との分岐点から見る(repo):
    commit(repo, "old.py", "y = 1  # DEBUG_ONLY\n")  # main に前からあるものでは止めない
    assert git(repo, "push", "-q", "--no-verify", "origin", "main").returncode == 0
    git(repo, "switch", "-q", "-c", "feat/1-a")
    commit(repo, "app.py", "x = 1\n")
    r = git(repo, "push", "-q", "-u", "origin", "feat/1-a")
    assert r.returncode == 0, r.stdout + r.stderr


def test_新しいブランチで足した禁止パターンは止める(repo):
    commit(repo, "app.py", "x = 1\n")
    assert git(repo, "push", "-q", "origin", "main").returncode == 0
    git(repo, "switch", "-q", "-c", "feat/2-b")
    commit(repo, "app.py", "x = 1  # DEBUG_ONLY\n")
    r = git(repo, "push", "-q", "-u", "origin", "feat/2-b")
    assert r.returncode != 0
    assert "no-debug" in r.stdout + r.stderr


def test_既にあるブランチは前のpushからの差分だけを見る(repo):
    commit(repo, "app.py", "x = 1\n")
    assert git(repo, "push", "-q", "origin", "main").returncode == 0
    git(repo, "switch", "-q", "-c", "feat/3-c")
    commit(repo, "a.py", "a = 1\n")
    assert git(repo, "push", "-q", "-u", "origin", "feat/3-c").returncode == 0
    commit(repo, "b.py", "b = 1  # DEBUG_ONLY\n")
    r = git(repo, "push", "-q", "origin", "feat/3-c")
    assert r.returncode != 0


def test_検査のスクリプトがなければ守るブランチだけを見る(repo):
    (repo / "scripts" / "check_forbidden.py").unlink()
    commit(repo, "app.py", "x = 1  # DEBUG_ONLY\n")
    r = git(repo, "push", "-q", "origin", "main")
    assert r.returncode == 0, r.stderr
