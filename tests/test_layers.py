"""層ごとの規約（templates/layers/*/CLAUDE.md）の形を検査する。"""

from __future__ import annotations

from pathlib import Path

import pytest

LAYERS = Path(__file__).resolve().parents[1] / "templates" / "layers"


@pytest.mark.parametrize("layer", ["web", "api", "batch", "db", "e2e"])
def test_層ごとの規約がある(layer):
    path = LAYERS / layer / "CLAUDE.md"
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 60  # 層の規約も短く保つ
    assert "## 止まって人へ戻す" in text
    assert "直下の CLAUDE.md" in text


@pytest.mark.parametrize("layer", ["api", "batch"])
def test_個人情報をログに出さないと書いてある(layer):
    assert "個人情報" in (LAYERS / layer / "CLAUDE.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("layer", ["web", "api", "db"])
def test_状態の値を直接書かないと書いてある(layer):
    text = (LAYERS / layer / "CLAUDE.md").read_text(encoding="utf-8")
    assert "カタログ" in text
