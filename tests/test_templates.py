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
    assert {p.parent.name for p in SKILLS} >= {
        "feature",
        "bugfix",
        "decision-memo",
        "impact",
        "verify",
        "spec-review",
        "review",
        "catalog-challenge",
        "harness-rule",
    }


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
    assert len(commands) == 4
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


def test_反証役はカタログの変更を崩す役で_reviewからも呼ばれる():
    agent = (CORE / ".claude" / "agents" / "catalog-challenger.md").read_text(encoding="utf-8")
    for way in ("重なり", "判定の抜け", "反例", "ほかの正本との食い違い", "変更が届かない所", "戻せるか"):
        assert way in agent, way
    review = (CORE / ".claude" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
    assert "catalog-challenger" in review


def test_決まりの一覧は_当てはまらない場合を必ず持つ():
    rules = (CORE / "docs" / "decisions" / "rules.md").read_text(encoding="utf-8")
    assert "| ID | 決まり | 当てはまらない場合（人へ戻す） | 元の決定 | 効く場所 |" in rules
    skill = (CORE / ".claude" / "skills" / "harness-rule" / "SKILL.md").read_text(encoding="utf-8")
    assert "当てはまらない場合" in skill and "採用するのは人" in skill
    claude = (CORE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/decisions/rules.md" in claude
    memo = (CORE / ".claude" / "skills" / "decision-memo" / "SKILL.md").read_text(encoding="utf-8")
    assert "docs/decisions/rules.md" in memo


def test_AIは判断チケットを自分で起票できる_決めるのは人():
    claude = (CORE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "gh issue create" in claude and "起票は AI がしてよい" in claude
    memo = (CORE / ".claude" / "skills" / "decision-memo" / "SKILL.md").read_text(encoding="utf-8")
    assert "AI からは呼べない" in memo and "起票してよい" in memo


def test_運用で見つかった穴を直してある():
    routes = json.loads((CORE / ".claude" / "review-routes.json").read_text(encoding="utf-8"))
    pats = [re.compile(p) for p in routes["reviewers"]["security"]["content"]]
    assert any(p.search('log.info("x", phone=row.phone)') for p in pats)  # F-2：log.info も個人情報の担当に回す
    owners = (CORE / "docs" / "decisions" / "owners.md").read_text(encoding="utf-8")
    assert "本物のチームの名前に置き換える" in owners  # F-4
    memo = (CORE / ".claude" / "skills" / "decision-memo" / "SKILL.md").read_text(encoding="utf-8")
    assert "外さずに" in memo and "書式つき" in memo  # F-5・F-4


def test_割り振りの担当すべてに観点の一覧がある():
    routes = json.loads((CORE / ".claude" / "review-routes.json").read_text(encoding="utf-8"))
    for name in list(routes["reviewers"]) + ["general"]:
        assert (CORE / ".claude" / "review" / f"{name}.md").exists(), name


def skill(name: str) -> str:
    return (CORE / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["feature", "bugfix"])
def test_決定はDECか仕様に書き戻してから実装し_最後に決定記録を書く(name):
    text = skill(name)
    assert "コメントは正本にしない" in text  # 穴1
    assert "決定記録を1本書く" in text
    for part in ("なぜ", "合意した範囲", "先送りしたもの", "根拠"):
        assert part in text, part
    assert "それぞれ main から作る" in text and "分割の途中ではチケットを閉じない" in text  # 穴4


def test_判断記録の型は_なぜ_範囲_先送り_根拠を持つ():
    text = (CORE / "docs" / "decisions" / "_template.md").read_text(encoding="utf-8")
    for head in ("## なぜ", "## 合意した範囲", "## 先送りしたものと理由", "## 根拠"):
        assert head in text, head


def test_PRテンプレートに関係するDECの欄がある():
    text = (CORE / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "## 関係する DEC" in text
    workflow = (CORE / ".github" / "workflows" / "pr-check.yml").read_text(encoding="utf-8")
    assert "check_dec_refs.py" in workflow


@pytest.mark.parametrize("name", ["review", "spec-review"])
def test_レビューは収束させる(name):
    text = skill(name)
    assert "前回からの差分と未解決の指摘だけ" in text  # 穴2
    assert "解決・見送り・新規" in text
    assert "重さの下限" in text and "1回の指摘の上限" in text
    assert "重大な新規が0の回が2回続いたら閉じる" in text
    assert "作業チケット" in text


def test_reviewはレビュー役を前景で動かし_そろうまで終えない():
    text = skill("review")
    assert "前景" in text and "全員の結果がそろってから" in text  # 穴5


def test_人と話さず動かすときの文書がある():
    text = (CORE / "docs" / "harness" / "headless.md").read_text(encoding="utf-8")
    for must in (
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1",
        "--permission-mode",
        "--settings",
        "--bare",
        "--output-format json",
        "--max-turns",
        "--max-budget-usd",
        "HARNESS_STOP_CHECK",
    ):
        assert must in text, must


def test_並べて進めるときの決まりがある():
    claude = (CORE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "git worktree" in claude and "fetch は親が1回" in claude  # 穴3
    doc = (CORE / "docs" / "harness" / "parallel.md").read_text(encoding="utf-8")
    for must in ("fetch", "自分のブランチ名", ".env", "1本ずつ順に", "${"):
        assert must in doc, must


def test_共通部品は人が認めたらAIが書く():
    claude = (CORE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "AI がテストを先に書いて共通部品だけの PR を作る" in claude  # 穴6
    assert "人が書くのではない" in claude
    for layer in ("api", "web"):
        text = (CORE.parent / "layers" / layer / "CLAUDE.md").read_text(encoding="utf-8")
        assert "共通部品だけの PR" in text, layer


def test_PRの大きさは本体とテストに分けて書く():
    claude = (CORE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "本体（テストを除く）400行" in claude and "テスト800行" in claude  # 穴8


def test_完了の条件のStopフックは既定で無効():
    hook = (CORE / ".claude" / "hooks" / "check-done-on-stop.py").read_text(encoding="utf-8")
    assert "HARNESS_STOP_CHECK" in hook and "make check" in hook
    settings = json.loads((CORE / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "HARNESS_STOP_CHECK" not in json.dumps(settings.get("env", {}))
