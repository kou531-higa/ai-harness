"""pre-push フックと merge_pr.py のテスト。gh は偽物に差し替える。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "templates" / "core"
PRE_PUSH = CORE / "scripts" / "git-hooks" / "pre-push"
MERGE = CORE / "scripts" / "merge_pr.py"


def push(lines: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, str(PRE_PUSH)], input=lines, capture_output=True, text=True, env=e)


def test_mainへのpushを止める():
    r = push("refs/heads/main abc refs/heads/main def\n")
    assert r.returncode == 1
    assert "make merge" in r.stderr


def test_作業ブランチとタグのpushは通す():
    r = push("refs/heads/feat/x abc refs/heads/feat/x 000\nrefs/tags/v1 abc refs/tags/v1 000\n")
    assert r.returncode == 0


def test_守るブランチを変えられる():
    r = push("refs/heads/release abc refs/heads/release def\n", {"HARNESS_PROTECTED_BRANCHES": "main,release"})
    assert r.returncode == 1


PR_OK = {
    "state": "OPEN",
    "isDraft": False,
    "labels": [],
    "mergeable": "MERGEABLE",
    "mergeStateStatus": "CLEAN",
    "headRefOid": "abc123",
    "title": "テスト",
}
CHECKS_OK = [{"name": "test", "state": "SUCCESS", "bucket": "pass"}, {"name": "pr-size", "bucket": "pass"}]


@pytest.fixture
def fake_gh(tmp_path: Path):
    def make(pr: dict, checks: list) -> dict:
        (tmp_path / "pr.json").write_text(json.dumps(pr), encoding="utf-8")
        (tmp_path / "checks.json").write_text(json.dumps(checks), encoding="utf-8")
        script = tmp_path / "gh"
        script.write_text(
            f"#!{sys.executable}\n"
            "import sys, pathlib\n"
            f"d = pathlib.Path({str(tmp_path)!r})\n"
            "a = sys.argv[1:]\n"
            "(d / 'calls.txt').open('a').write(' '.join(a) + '\\n')\n"
            "if a[:2] == ['pr', 'view']: print((d / 'pr.json').read_text())\n"
            "elif a[:2] == ['pr', 'checks']: print((d / 'checks.json').read_text())\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return {"HARNESS_GH": str(script)}

    return make


def merge(tmp_path: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    e = dict(os.environ, **env)
    return subprocess.run(
        [sys.executable, str(MERGE), *args], capture_output=True, text=True, env=e, cwd=tmp_path, check=False
    )


def calls(tmp_path: Path) -> str:
    return (tmp_path / "calls.txt").read_text()


def test_すべて緑ならsquashでマージする(tmp_path, fake_gh):
    r = merge(tmp_path, fake_gh(PR_OK, CHECKS_OK), "12")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pr merge 12 --squash --delete-branch --match-head-commit abc123" in calls(tmp_path)
    assert (tmp_path / ".harness/events.jsonl").exists()


@pytest.mark.parametrize(
    "pr_change, checks, reason",
    [
        ({}, [{"name": "test", "bucket": "fail"}], "test が fail"),
        ({}, [{"name": "test", "bucket": "pending"}], "test が pending"),
        ({}, [], "検査が1つもありません"),
        ({"isDraft": True}, CHECKS_OK, "下書き"),
        ({"labels": [{"name": "needs-decision"}]}, CHECKS_OK, "needs-decision"),
        ({"mergeStateStatus": "BEHIND"}, CHECKS_OK, "遅れています"),
        ({"state": "MERGED"}, CHECKS_OK, "開いていません"),
    ],
)
def test_条件を満たさなければマージしない(tmp_path, fake_gh, pr_change, checks, reason):
    r = merge(tmp_path, fake_gh({**PR_OK, **pr_change}, checks), "12")
    assert r.returncode == 1
    assert reason in r.stdout
    assert "pr merge" not in calls(tmp_path)


def test_dry_runはマージしない(tmp_path, fake_gh):
    r = merge(tmp_path, fake_gh(PR_OK, CHECKS_OK), "12", "--dry-run")
    assert r.returncode == 0
    assert "pr merge" not in calls(tmp_path)


def test_番号でなければ止める(tmp_path, fake_gh):
    assert merge(tmp_path, fake_gh(PR_OK, CHECKS_OK), "").returncode == 2
