"""配布するテンプレートの形を検査する（のちの harness check の元になる）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

CORE = Path(__file__).resolve().parents[1] / "templates" / "core"
SKILLS = sorted((CORE / ".claude" / "skills").glob("*/SKILL.md"))
AI_STOP_REASONS = {
    "spec-undecided",
    "spec-conflict",
    "customer-agreement",
    "uncovered",
    "two-failures",
    "shared-component",
    "pr-too-large",
    "irreversible",
    "security",
    "other",
}


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path} に frontmatter がない"
    return yaml.safe_load(m.group(1))


def test_CLAUDE_mdは150行以内():
    lines = (CORE / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150


def test_スキルが3つある():
    assert {p.parent.name for p in SKILLS} >= {"feature", "bugfix", "decision-memo", "impact", "verify", "spec-review"}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_スキルのfrontmatter(skill):
    fm = frontmatter(skill)
    assert fm["name"] == skill.parent.name
    assert fm["description"]
    # 副作用があるので、AI が勝手に呼ばないようにする
    assert fm["disable-model-invocation"] is True


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_スキルに終わる条件と止まる条件がある(skill):
    text = skill.read_text(encoding="utf-8")
    assert "## 手順" in text
    assert "## 終わってよい条件" in text
    assert "## 止まって人へ戻す条件" in text


@pytest.mark.parametrize(
    "path", [CORE / "CLAUDE.md", *SKILLS], ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name
)
def test_ai_stopの理由は決められた一覧から選ぶ(path):
    text = path.read_text(encoding="utf-8")
    reasons = set(re.findall(r"\| `([a-z-]+)`", text))  # 止まる条件の表
    reasons |= set(re.findall(r"ai-stop:([a-z-]+)", text))  # ai-stop:spec-conflict のような直書き
    assert reasons <= AI_STOP_REASONS, reasons - AI_STOP_REASONS
    if path.parent.name in ("feature", "bugfix"):
        assert reasons, "止まる条件の表に理由がない"


def test_settingsのフックが実在する():
    settings = json.loads((CORE / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
    assert len(commands) == 3
    for cmd in commands:
        script = re.search(r"\.claude/hooks/([\w-]+\.py)", cmd).group(1)
        assert (CORE / ".claude" / "hooks" / script).exists(), script


def test_settingsはapplyとマージを禁止する():
    deny = json.loads((CORE / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
    for must in ("Bash(terraform apply:*)", "Bash(gh pr merge:*)", "Bash(git push --force:*)", "Read(./.env)"):
        assert must in deny


@pytest.mark.parametrize("path", sorted((CORE / ".github").rglob("*.yml")), ids=lambda p: p.name)
def test_YAMLとして読める(path):
    assert yaml.safe_load(path.read_text(encoding="utf-8"))


def test_判断事項のフォームは4項目と決定者と期限を必須にする():
    form = yaml.safe_load((CORE / ".github" / "ISSUE_TEMPLATE" / "decision.yml").read_text(encoding="utf-8"))
    required = {b["id"] for b in form["body"] if b.get("validations", {}).get("required")}
    assert required == {"issue", "options", "recommendation", "owner", "due"}
    assert "needs-decision" in form["labels"]


def test_PRテンプレートに判断すべき点と証拠がある():
    text = (CORE / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "## 人が判断すべき点" in text
    assert "## 証拠" in text


def test_CLAUDE_mdは理由の一覧をすべて載せる():
    text = (CORE / "CLAUDE.md").read_text(encoding="utf-8")
    for reason in AI_STOP_REASONS:
        assert f"`{reason}`" in text, reason


def test_featureは大きい変更のときだけ計画の承認を待つ():
    text = (CORE / ".claude" / "skills" / "feature" / "SKILL.md").read_text(encoding="utf-8")
    assert "大きい変更のときだけ" in text
    assert "400行を超えそう" in text


@pytest.mark.parametrize("name", ["feature", "bugfix"])
def test_変える前に今の振る舞いを固定する(name):
    text = (CORE / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    assert "今の振る舞いを固定する" in text


def test_decision_memoは決定者マップを使う():
    text = (CORE / ".claude" / "skills" / "decision-memo" / "SKILL.md").read_text(encoding="utf-8")
    assert "docs/decisions/owners.md" in text


AGENTS = sorted((CORE / ".claude" / "agents").glob("*.md"))


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_レビュー役は読むだけ(agent):
    fm = frontmatter(agent)
    assert fm["name"] == agent.stem
    assert fm["description"]
    tools = {t.strip() for t in fm["tools"].split(",")}
    assert not tools & {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def test_仕様レビュー役がある():
    assert (CORE / ".claude" / "agents" / "spec-reviewer.md").exists()
    assert (CORE / ".claude" / "skills" / "spec-review" / "SKILL.md").exists()
