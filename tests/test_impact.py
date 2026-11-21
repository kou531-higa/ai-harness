"""impact.py のテスト。一時的な git リポジトリで動かす。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "templates" / "core" / "scripts" / "impact.py"

FILES = {
    "api/src/orders/orders.ts": "const sql = \"status in ('ACCEPTED','READY')\";\n",
    "api/src/orders/orders.spec.ts": "it('ACCEPTED は対象', () => {});\n",
    "db/procedures/close.sql": "where status in ('ACCEPTED','READY') or status = 'ON_HOLD'\n",
    "web/src/app/page.tsx": "const ready = ['ACCEPTED', 'READY', 'COMPLETED'];\n",
    "docs/specs/states.md": "| ACCEPTED | 検収済み |\n",
    "api/package-lock.json": '{"ACCEPTED": 1}\n',
    "batch/commands/unrelated.py": "print('nothing')\n",
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=repo, capture_output=True, text=True, check=False)


def data(repo: Path, *terms: str) -> dict:
    return json.loads(run(repo, *terms, "--json").stdout)


def test_層と種類に分ける(repo):
    hits = {h["file"]: (h["layer"], h["kind"]) for h in data(repo, "ACCEPTED")["hits"]}
    assert hits["api/src/orders/orders.ts"] == ("api", "コード")
    assert hits["api/src/orders/orders.spec.ts"] == ("api", "テスト")
    assert hits["db/procedures/close.sql"] == ("db", "SQL")
    assert hits["docs/specs/states.md"] == ("docs", "仕様・文書")


def test_ロックファイルは探さない(repo):
    assert "api/package-lock.json" not in {h["file"] for h in data(repo, "ACCEPTED")["hits"]}


def test_テストのない層を出す(repo):
    assert data(repo, "ACCEPTED")["untested_layers"] == ["web", "db"]


def test_複数の言葉のどれに当たったかを書く(repo):
    hits = {h["file"]: h["terms"] for h in data(repo, "ON_HOLD", "COMPLETED")["hits"]}
    assert hits == {"db/procedures/close.sql": ["ON_HOLD"], "web/src/app/page.tsx": ["COMPLETED"]}


def test_表で出し_テストのない所を案内する(repo):
    out = run(repo, "ACCEPTED").stdout
    assert "| api | 1 | 0 | 1 | 0 |" in out
    assert "テストなし" in out and "固定するテスト" in out
