"""review_route.py のテスト。一時的な git リポジトリで、main から枝を切って変更する。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "templates" / "core"
SCRIPT = CORE / "scripts" / "review_route.py"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".claude").mkdir()
    shutil.copy(CORE / ".claude" / "review-routes.json", tmp_path / ".claude" / "review-routes.json")
    write(tmp_path, "README.md", "x\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    git(tmp_path, "switch", "-q", "-c", "feat")
    return tmp_path


def plan(repo: Path, files: dict) -> dict:
    for rel, text in files.items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main", "--json"], cwd=repo, capture_output=True, text=True, check=True
    )
    return json.loads(r.stdout)


def test_場所で担当を選ぶ(repo):
    p = plan(repo, {"api/src/x.ts": "export const a = 1;\n", "api/src/x.spec.ts": "it('a', () => {});\n"})
    assert p["reviewers"]["api"] == ["api/src/x.spec.ts", "api/src/x.ts"]
    assert p["reviewers"]["test"] == ["api/src/x.spec.ts"]


def test_中身で担当を足す_個人情報と状態名(repo):
    p = plan(repo, {"batch/commands/imp.py": "click.echo(row.customer_phone)\nif s == 'ON_HOLD': pass\n"})
    assert "batch/commands/imp.py" in p["reviewers"]["security"]
    assert "batch/commands/imp.py" in p["reviewers"]["state"]
    assert p["reasons"]["security"]["batch/commands/imp.py"] == ["中身"]


def test_どの担当も見ないファイルは未カバー(repo):
    p = plan(repo, {"Makefile": "x:\n\techo\n", "web/a.tsx": "export {};\n"})
    assert p["uncovered"] == ["Makefile"]
    assert p["critical_uncovered"] == []


def test_重要な所が未カバーならstrictで止める(repo):
    cfg = repo / ".claude" / "review-routes.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    del data["reviewers"]["db"]
    cfg.write_text(json.dumps(data), encoding="utf-8")
    git(repo, "commit", "-qam", "db の担当を外す")
    plan(repo, {"db/migrations/0002.sql": "create table t (id int);\n"})
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main", "--strict"], cwd=repo, capture_output=True, text=True
    )
    assert r.returncode == 1
    assert "重要な所で未カバー：db/migrations/0002.sql" in r.stdout


def test_重要な所の変更は人も見るよう出す(repo):
    p = plan(repo, {"api/src/common/log.ts": "export {};\n"})
    assert p["critical_changed"] == ["api/src/common/log.ts"]
    assert p["critical_uncovered"] == []


def test_消しただけのファイルも数える(repo):
    (repo / "README.md").unlink()
    p = plan(repo, {})
    assert p["files"] == ["README.md"]
    assert p["uncovered"] == ["README.md"]
