"""check_forbidden.py のテスト。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "templates" / "core"
SCRIPT = CORE / "scripts" / "check_forbidden.py"
STATES = ["ACCEPTED", "READY", "ON_HOLD", "COMPLETED"]


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
    cfg = json.loads((CORE / ".claude" / "forbidden-patterns.json").read_text(encoding="utf-8"))
    cfg["states"] = STATES
    (tmp_path / ".claude" / "forbidden-patterns.json").write_text(json.dumps(cfg), encoding="utf-8")
    write(tmp_path, "api/src/old.ts", "const ready = ['ACCEPTED', 'READY'];\n")  # 導入前からある
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    git(tmp_path, "switch", "-q", "-c", "feat")
    return tmp_path


def run(repo: Path, files: dict, *args: str) -> subprocess.CompletedProcess:
    for rel, text in files.items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "change")
    cmd = [sys.executable, str(SCRIPT), "--base", "main", "--json", *args]
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)


def rules(r: subprocess.CompletedProcess) -> list:
    return [(x["rule"], x["file"], x["line"]) for x in json.loads(r.stdout)["items"]]


def test_状態名を2つ以上並べた判定を見つける(repo):
    r = run(repo, {"api/src/orders.ts": "x\nwhere status in ('ACCEPTED','READY')\n"})
    assert r.returncode == 1
    assert rules(r) == [("state-list", "api/src/orders.ts", 2)]


def test_状態名が1つだけなら当たらない(repo):
    r = run(repo, {"api/src/x.ts": "if (s === 'ON_HOLD') {}\n"})
    assert r.returncode == 0


def test_導入前からある行では止めない_allなら数える(repo):
    assert run(repo, {}).returncode == 0
    r = run(repo, {}, "--all")
    assert rules(r) == [("state-list", "api/src/old.ts", 1)]


def test_テストとカタログは対象外(repo):
    r = run(repo, {"api/src/x.spec.ts": "['ACCEPTED','READY']\n", "catalog/states.ts": "['ACCEPTED','READY']\n"})
    assert r.returncode == 0


def test_自作のページングとSQLの組み立てを見つける(repo):
    r = run(
        repo,
        {
            "api/src/list.ts": "qb.skip((page - 1) * pageSize)\n",
            "batch/commands/x.py": 'cur.execute(f"select * from t where id = {i}")\n',
        },
    )
    assert {x[0] for x in rules(r)} == {"self-paging", "sql-format"}


def test_理由付きの例外は通し_理由のない例外は通さない(repo):
    ok = "const a = ['ACCEPTED','READY']; // forbidden-ok: state-list 表示の並び順だけに使う\n"
    assert run(repo, {"web/a.ts": ok}).returncode == 0
    r = run(repo, {"web/b.ts": "const b = ['ACCEPTED','READY']; // forbidden-ok: state-list\n"})
    assert r.returncode == 1


def test_状態の一覧が空なら状態の決まりは使わない(repo):
    cfg = repo / ".claude" / "forbidden-patterns.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["states"] = []
    cfg.write_text(json.dumps(data), encoding="utf-8")
    assert run(repo, {"api/src/y.ts": "['ACCEPTED','READY']\n"}).returncode == 0
