from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_spec_consistency", ROOT / "templates" / "core" / "scripts" / "check_spec_consistency.py"
)
cc = importlib.util.module_from_spec(_spec)
sys.modules["check_spec_consistency"] = cc
_spec.loader.exec_module(cc)

FUNCS = """# 機能一覧

| 画面ID | 画面名 | 表示件数 | 遷移先 |
|---|---|---|---|
| SCR-001 | 依頼一覧 | 50 | SCR-002 |
| SCR-002 | 依頼詳細 | - | SCR-001、SCR-003 |
| SCR-003 | 手配 | - | SCR-002 |
"""

DIAGRAM = """```mermaid
flowchart LR
  SCR-001 --> SCR-002
  SCR-002 --> SCR-001
  SCR-002 -->|手配する| SCR-003
  SCR-003 --> SCR-002
```
"""


def screen(sid: str, transitions: str, page_size: str = "") -> str:
    ps = f"page_size: {page_size}\n" if page_size else ""
    return f"---\nid: {sid}\n{ps}transitions: {transitions}\n---\n# {sid}\n"


@pytest.fixture
def specs(tmp_path: Path) -> Path:
    (tmp_path / "screens").mkdir()
    (tmp_path / "usecases").mkdir()
    (tmp_path / "functions.md").write_text(FUNCS, encoding="utf-8")
    (tmp_path / "transitions.md").write_text(DIAGRAM, encoding="utf-8")
    (tmp_path / "screens" / "SCR-001.md").write_text(screen("SCR-001", "SCR-002", "50"), encoding="utf-8")
    (tmp_path / "screens" / "SCR-002.md").write_text(screen("SCR-002", "SCR-001, SCR-003"), encoding="utf-8")
    (tmp_path / "screens" / "SCR-003.md").write_text(screen("SCR-003", "SCR-002"), encoding="utf-8")
    (tmp_path / "usecases" / "UC-001.md").write_text("---\nscreens: SCR-001, SCR-002\n---\n", encoding="utf-8")
    return tmp_path


def kinds(specs: Path) -> list:
    return [f.kind for f in cc.check(specs)]


def test_揃っていれば0件(specs):
    assert cc.check(specs) == []
    assert cc.main([str(specs)]) == 0


def test_画面仕様のない画面IDを見つける(specs):
    (specs / "screens" / "SCR-003.md").unlink()
    found = cc.check(specs)
    assert any(f.kind == "画面ID" and "SCR-003 は機能一覧にあるが" in f.detail for f in found)


def test_機能一覧にない画面を見つける(specs):
    (specs / "screens" / "SCR-009.md").write_text(screen("SCR-009", ""), encoding="utf-8")
    assert "画面ID" in kinds(specs)


def test_表示件数のずれを見つける(specs):
    (specs / "screens" / "SCR-001.md").write_text(screen("SCR-001", "SCR-002", "100"), encoding="utf-8")
    found = cc.check(specs)
    assert [f.detail for f in found if f.kind == "件数"] == ["SCR-001 の表示件数：機能一覧は 50、画面仕様は 100"]


def test_遷移先のずれを見つける_遷移図だけ違う(specs):
    (specs / "transitions.md").write_text(DIAGRAM.replace("  SCR-003 --> SCR-002\n", ""), encoding="utf-8")
    found = [f for f in cc.check(specs) if f.kind == "遷移先"]
    assert len(found) == 1
    assert "SCR-003" in found[0].detail and "遷移図 なし" in found[0].detail


def test_ユースケースが存在しない画面を参照(specs):
    (specs / "usecases" / "UC-002.md").write_text("---\nscreens: SCR-001, SCR-404\n---\n", encoding="utf-8")
    assert any("SCR-404" in f.detail for f in cc.check(specs))


def test_食い違いがあればexit1と人へ戻す案内(specs, capsys):
    (specs / "screens" / "SCR-001.md").write_text(screen("SCR-001", "SCR-002", "100"), encoding="utf-8")
    assert cc.main([str(specs)]) == 1
    out = capsys.readouterr().out
    assert "食い違い: 1件" in out and "人が決めます" in out


def test_JSONで一覧を出す(specs, capsys):
    (specs / "screens" / "SCR-003.md").unlink()
    assert cc.main([str(specs), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == len(data["items"]) >= 1
    assert {"kind", "where", "detail"} <= set(data["items"][0])
