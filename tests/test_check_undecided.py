from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_undecided", ROOT / "templates" / "core" / "scripts" / "check_undecided.py"
)
cu = importlib.util.module_from_spec(_spec)
sys.modules["check_undecided"] = cu
_spec.loader.exec_module(cu)

GOOD = """---
id: SPEC-001
status: review        # draft → review → approved
owner: '@po-tanaka'
---
## 目的
受注担当者が、今日の受注を一覧で確かめられる。

## 対象外
- CSV出力（SPEC-004で扱う）

## 合格基準
- AC-001-1 Given 受注0件 When 一覧を開く
           Then「該当する受注はありません」
- AC-001-3 Given 取消済み When 一覧を開く Then 状態に「取消」と表示

```
例: この中の TBD は数えない
```
"""


def write(tmp_path: Path, text: str, name: str = "SPEC-001.md") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_条件を満たす仕様は通る(tmp_path):
    write(tmp_path, GOOD)
    assert cu.main([str(tmp_path), "--require", "approved"]) == 0


def test_frontmatterを読む(tmp_path):
    r = cu.analyze(write(tmp_path, GOOD))
    assert r.spec_id == "SPEC-001"
    assert r.status == "review"


def test_未確定があれば止める_ACのIDつきで報告(tmp_path, capsys):
    text = GOOD.replace(
        "- AC-001-3", "- AC-001-2 Given 受注101件 When 一覧を開く\n           Then 1ページに TBD 件\n- AC-001-3"
    )
    write(tmp_path, text)
    assert cu.main([str(tmp_path), "--require", "approved"]) == 1
    out = capsys.readouterr().out
    assert "SPEC-001（review）" in out
    assert "未確定 AC-001-2" in out


def test_コードブロックの中は数えない(tmp_path):
    r = cu.analyze(write(tmp_path, GOOD))
    assert r.markers == []


def test_draftは承認の検査をしない(tmp_path):
    write(tmp_path, GOOD.replace("status: review", "status: draft").replace("合格基準", "基準"))
    assert cu.main([str(tmp_path), "--require", "approved"]) == 0


def test_requireなしなら一覧だけ出してexit0(tmp_path, capsys):
    write(tmp_path, GOOD.replace("受注0件", "受注 要確認 件"))
    assert cu.main([str(tmp_path)]) == 0
    assert "未確定 1件" in capsys.readouterr().out


def test_GivenWhenThenの欠落を検出(tmp_path):
    r = cu.analyze(write(tmp_path, GOOD.replace(" When 一覧を開く Then 状態に", " 状態に")))
    assert "AC-001-3: When／Then がない" in r.format_errors


def test_IDのない合格基準を検出(tmp_path):
    r = cu.analyze(write(tmp_path, GOOD.replace("- AC-001-3 ", "- ")))
    assert any("ID（AC-001-1 の形）がない" in e for e in r.format_errors)


def test_対象外の節がなければ検出(tmp_path):
    r = cu.analyze(write(tmp_path, GOOD.replace("## 対象外", "## その他")))
    assert "「## 対象外」の節がない" in r.format_errors


def test_判断チケットへのリンクを認識(tmp_path):
    r = cu.analyze(write(tmp_path, GOOD.replace("受注0件", "受注 TBD 件（decision: #12）")))
    assert len(r.markers) == 1
    assert r.markers[0].linked is True


def test_テンプレートは飛ばす(tmp_path):
    write(tmp_path, GOOD.replace("受注0件", "TBD"), name="_template.md")
    assert cu.main([str(tmp_path), "--require", "approved"]) == 0


@pytest.mark.parametrize(
    "text,kind",
    [
        ("件数は TBD", "TBD"),
        ("上限は要確認", "要確認"),
        ("扱いは【保留】", "保留"),
        ("保留：取引先と相談中", "保留"),
        ("TODO 文字コードを決める", "TODO"),
        ("顧客の確認待ち", "確認待ち"),
        ("（この節は書きかけ）", "書きかけ"),
    ],
)
def test_5つの印を種類つきで拾う(tmp_path, text, kind):
    r = cu.analyze(write(tmp_path, GOOD.replace("受注0件", text)))
    assert [m.kind for m in r.markers] == [kind]


@pytest.mark.parametrize("text", ["状態が保留の依頼は除く", "保留中の依頼", "TODOS は単語の一部", "TBDX"])
def test_状態の名前の保留や単語の一部は拾わない(tmp_path, text):
    r = cu.analyze(write(tmp_path, GOOD.replace("受注0件", text)))
    assert r.markers == []


def test_JSONで台帳に入れる形を出す(tmp_path, capsys):
    import json

    write(tmp_path, GOOD.replace("受注0件", "件数は TBD"))
    assert cu.main([str(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 1
    item = data["items"][0]
    assert item["kind"] == "TBD" and item["spec"] == "SPEC-001" and item["ac"] == "AC-001-1"
