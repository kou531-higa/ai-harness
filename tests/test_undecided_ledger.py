"""未決事項台帳のテスト。scripts をそのまま別プロセスで実行する。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "templates" / "core" / "scripts"

SPEC = """---
id: SPEC-010
status: draft
owner: '@customer'
---
# SPEC-010

## 目的
- 文字コード：TBD
- 頻度は確認待ち decision: #12

## 対象外
- なし

## 合格基準
- AC-010-1 Given a When b Then c
"""

OWNERS = """# 決定者マップ

| 判断の種類 | 決定者 | 期限 |
|---|---|---|
| 仕様の未確定 | @owner-default | 2営業日 |
| 仕様の食い違い | @pm | 2営業日 |
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copytree(SCRIPTS, tmp_path / "scripts")
    (tmp_path / "docs/specs").mkdir(parents=True)
    (tmp_path / "docs/decisions").mkdir(parents=True)
    (tmp_path / "docs/specs/SPEC-010.md").write_text(SPEC, encoding="utf-8")
    (tmp_path / "docs/decisions/owners.md").write_text(OWNERS, encoding="utf-8")
    return tmp_path


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/undecided_ledger.py", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def ledger(repo: Path) -> str:
    return (repo / "docs/decisions/undecided.md").read_text(encoding="utf-8")


def test_未確定を台帳に載せ_決定者とチケットを書く(repo):
    assert run(repo).returncode == 0
    text = ledger(repo)
    assert "未確定 2件・食い違い 0件" in text
    assert "未確定（TBD）" in text and "未確定（確認待ち）" in text
    assert "@customer" in text  # 仕様の owner を優先
    assert "#12" in text and "未起票" in text
    assert "docs/specs/SPEC-010.md:9" in text


def test_ownerがなければ決定者マップから選ぶ(repo):
    p = repo / "docs/specs/SPEC-010.md"
    p.write_text(p.read_text(encoding="utf-8").replace("owner: '@customer'\n", ""), encoding="utf-8")
    run(repo)
    assert "@owner-default" in ledger(repo)


def test_IDは作り直しても変わらない(repo):
    run(repo)
    first = ledger(repo)
    run(repo)
    assert ledger(repo) == first


def test_checkは仕様が変わって台帳が古ければ止める(repo):
    run(repo)
    assert run(repo, "--check").returncode == 0
    p = repo / "docs/specs/SPEC-010.md"
    p.write_text(p.read_text(encoding="utf-8") + "- 期限は要確認\n", encoding="utf-8")
    r = run(repo, "--check")
    assert r.returncode == 1
    assert "作り直して" in r.stdout


def test_食い違いも載せる(repo):
    (repo / "docs/specs/functions.md").write_text(
        "| 画面ID | 画面名 | 表示件数 | 遷移先 |\n|---|---|---|---|\n| SCR-001 | 一覧 | 20 | - |\n", encoding="utf-8"
    )
    run(repo)
    text = ledger(repo)
    assert "食い違い 1件" in text
    assert "食い違い（画面ID）" in text and "@pm" in text
