"""harness doctor：リポジトリを、DORA の AI の7つの能力で 0〜3点に診断する。

観点ごとに、ファイルと GitHub の PR から確かめられる基準を3つ置き、満たした数を点にする。
点ごとに根拠（どのファイル・どの数を見たか）を必ず出す。確かめられない基準は「測れない」として点に入れない。
出典：DORA AI Capabilities Model（2025）。7つの名前は日本語に訳したもの。
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

GH = Callable[[List[str], Path], Optional[list]]


@dataclass
class Criterion:
    text: str
    ok: Optional[bool]  # None は測れない
    evidence: str
    fix: str = ""  # 満たしていないとき、ハーネスのどれで埋められるか


@dataclass
class Capability:
    name: str
    criteria: List[Criterion] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(1 for c in self.criteria if c.ok)

    @property
    def measured(self) -> int:
        return sum(1 for c in self.criteria if c.ok is not None)


def default_gh(args: List[str], cwd: Path) -> Optional[list]:
    """診断するリポジトリの場所で gh を動かす（-R がなければ、そのリポジトリの PR を読む）"""
    exe = os.environ.get("HARNESS_GH", "gh")
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, check=False, cwd=str(cwd))
    except OSError:
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def _read(root: Path, rel: str) -> Optional[str]:
    p = root / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


def _workflows(root: Path) -> str:
    d = root / ".github" / "workflows"
    return (
        "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(d.glob("*.y*ml")))
        if d.is_dir()
        else ""
    )


def _specs(root: Path) -> List[Path]:
    d = root / "docs" / "specs"
    return sorted(p for p in d.rglob("*.md") if not p.name.startswith("_")) if d.is_dir() else []


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def diagnose(root: Path, gh: GH = default_gh, repo: Optional[str] = None) -> List[Capability]:
    root = root.resolve()
    claude = _read(root, "CLAUDE.md")
    settings = _read(root, ".claude/settings.json") or ""
    wf = _workflows(root)
    specs = _specs(root)
    skills = sorted((root / ".claude" / "skills").glob("*/SKILL.md"))
    repo_args = ["-R", repo] if repo else []
    prs = gh(
        [
            "pr",
            "list",
            *repo_args,
            "--state",
            "merged",
            "--limit",
            "100",
            "--json",
            "number,additions,deletions,mergedAt",
        ],
        root,
    )
    caps: List[Capability] = []

    # 1. AI の方針が明確で伝わっている
    lines = len(claude.splitlines()) if claude else 0
    try:
        deny = json.loads(settings).get("permissions", {}).get("deny", []) if settings else []
    except json.JSONDecodeError:
        deny = []
    caps.append(Capability("AIの方針が明確で伝わっている", [
        Criterion("CLAUDE.md がある", claude is not None, "CLAUDE.md" if claude else "CLAUDE.md がない", "harness init（CLAUDE.md の雛形）"),
        Criterion("CLAUDE.md が150行以内", bool(claude) and lines <= 150, f"{lines}行", "手順はスキルに、層の作法は層の CLAUDE.md に分ける"),
        Criterion("禁止する操作を設定で止めている（permissions.deny）", len(deny) > 0, f".claude/settings.json の deny {len(deny)}件",
                  "harness init（settings.json）"),
    ]))  # fmt: skip

    # 2. データが整っている（仕様の正本が1つで、未確定と食い違いを機械で見つける）
    with_status = [
        p for p in specs if re.search(r"^status:\s*\S+", p.read_text(encoding="utf-8", errors="replace"), re.M)
    ]
    caps.append(Capability("データが整っている", [
        Criterion("仕様の正本の置き場所がある（docs/specs）", bool(specs), f"docs/specs の Markdown {len(specs)}件", "仕様を docs/specs に集める"),
        Criterion("仕様に状態（status）がある", bool(specs) and len(with_status) > 0,
                  f"status のある仕様 {len(with_status)}件／{len(specs)}件", "仕様の frontmatter に status（draft・approved）"),
        Criterion("CI が未確定と食い違いを検査している", "check_undecided" in wf and "check_spec_consistency" in wf,
                  "workflows に check_undecided・check_spec_consistency " + ("あり" if "check_undecided" in wf else "なし"),
                  "pr-check.yml の specs ジョブ"),
    ]))  # fmt: skip

    # 3. 社内の情報に AI が届く（手順・判断の記録・決定者を AI が読める）
    caps.append(Capability("社内の情報にAIが届く", [
        Criterion("手順がスキルになっている", len(skills) >= 3, f".claude/skills {len(skills)}件", "harness init（スキル）"),
        Criterion("判断の記録と決定者マップがある", (root / "docs/decisions/owners.md").is_file(),
                  "docs/decisions/owners.md " + ("あり" if (root / "docs/decisions/owners.md").is_file() else "なし"), "決定者マップ"),
        Criterion("判断の基準が決まりの一覧になっている", (root / "docs/decisions/rules.md").is_file(),
                  "docs/decisions/rules.md " + ("あり" if (root / "docs/decisions/rules.md").is_file() else "なし"), "/harness-rule"),
    ]))  # fmt: skip

    # 4. バージョン管理が強い
    hooks = (_git(root, "rev-parse", "--git-path", "hooks") or "").strip()
    hook = (
        (Path(hooks) if Path(hooks).is_absolute() else root / hooks) / "pre-push"
        if hooks
        else root / ".git/hooks/pre-push"
    )
    first_parent = _git(root, "log", "--first-parent", "--format=%s", "-n", "200", "HEAD")
    subjects = first_parent.splitlines() if first_parent else []
    via_pr = [s for s in subjects if re.search(r"\(#\d+\)$|^Merge pull request #\d+", s)]
    caps.append(Capability("バージョン管理が強い", [
        Criterion("main への直接の push を止めている", hook.is_file(), "pre-push フック " + ("あり" if hook.is_file() else "なし"),
                  "harness init（pre-push）。有料プランならブランチ保護"),
        Criterion("検査が緑のときだけマージする入口がある", (root / "scripts/merge_pr.py").is_file(),
                  "scripts/merge_pr.py " + ("あり" if (root / "scripts/merge_pr.py").is_file() else "なし"), "make merge PR=<番号>"),
        Criterion("今のブランチの履歴の9割が PR 経由", (len(via_pr) / len(subjects) >= 0.9) if len(subjects) >= 5 else None,
                  f"直近 {len(subjects)}件のうち PR 経由 {len(via_pr)}件" if len(subjects) >= 5 else "履歴が5件未満で測れない",
                  "1PR＝1チケットでマージする"),
    ]))  # fmt: skip

    # 5. 小さく出している
    sizes = [p["additions"] + p["deletions"] for p in prs] if prs else []
    median = statistics.median(sizes) if sizes else None
    caps.append(Capability("小さく出している", [
        Criterion("PR の行数を CI で検査している", "check_pr_size" in wf, "workflows に check_pr_size " + ("あり" if "check_pr_size" in wf else "なし"),
                  "pr-check.yml の pr-size ジョブ"),
        Criterion("マージした PR の行数の中央値が400行以内", (median <= 400) if median is not None else None,
                  f"中央値 {median:g}行（{len(sizes)}件）" if median is not None else "マージした PR がない、または gh で読めない",
                  "分けて出す（/feature は400行を超えそうなら分割案を出して止まる）"),
        Criterion("マージした PR の行数の中央値が200行以内", (median <= 200) if median is not None else None,
                  f"中央値 {median:g}行" if median is not None else "測れない", "生成物を数えない・共通部品を使う"),
    ]))  # fmt: skip

    # 6. 利用者を見ている（仕様に目的・対象外・測れる合格基準がある）
    def has(p: Path, pat: str) -> bool:
        return bool(re.search(pat, p.read_text(encoding="utf-8", errors="replace"), re.M))

    feature_specs = [p for p in specs if re.match(r"SPEC-\d+", p.name)]
    n = len(feature_specs)
    caps.append(Capability("利用者を見ている", [
        Criterion("機能の仕様（SPEC-xxx）に目的がある", n > 0 and all(has(p, r"^## 目的") for p in feature_specs),
                  f"目的のある仕様 {sum(has(p, r'^## 目的') for p in feature_specs)}件／{n}件", "仕様の型（目的・対象外・合格基準）"),
        Criterion("機能の仕様に対象外がある", n > 0 and all(has(p, r"^## 対象外") for p in feature_specs),
                  f"対象外のある仕様 {sum(has(p, r'^## 対象外') for p in feature_specs)}件／{n}件", "仕様の型"),
        Criterion("合格基準が Given／When／Then で書かれている", n > 0 and all(has(p, r"Given .+When .+Then") for p in feature_specs),
                  f"Given／When／Then のある仕様 {sum(has(p, r'Given .+When .+Then') for p in feature_specs)}件／{n}件",
                  "check_undecided.py --require approved"),
    ]))  # fmt: skip

    # 7. 社内プラットフォームの質（品質ゲートと共通部品を全員が同じ形で使う）
    common = [d for d in ("api/src/common", "web/src/lib", "batch/core", "src/common", "lib") if (root / d).is_dir()]
    caps.append(Capability("社内プラットフォームの質", [
        Criterion("PR で CI が動く", "pull_request" in wf, ".github/workflows に pull_request " + ("あり" if "pull_request" in wf else "なし"),
                  "pr-check.yml"),
        Criterion("手元と CI で同じ検査の入口がある（make check）", "check:" in (_read(root, "Makefile") or ""),
                  "Makefile の check " + ("あり" if "check:" in (_read(root, "Makefile") or "") else "なし"), "Makefile に check"),
        Criterion("共通部品の置き場所がある", bool(common), "、".join(common) or "見つからない", "ログ・DB・ページングなどの共通部品をまとめる"),
    ]))  # fmt: skip
    return caps


def render(caps: List[Capability], root: Path) -> str:
    total = sum(c.score for c in caps)
    out = [
        f"# harness doctor：{root.name}",
        "",
        f"合計 {total}点／{3 * len(caps)}点（DORA の AI の7つの能力。各0〜3点）",
        "",
    ]
    out += ["| 能力 | 点 | 測れなかった基準 |", "|---|---|---|"]
    out += [f"| {c.name} | {c.score} | {3 - c.measured} |" for c in caps]
    for c in caps:
        out += ["", f"## {c.name}：{c.score}点", ""]
        for k in c.criteria:
            mark = "測れない" if k.ok is None else ("満たす" if k.ok else "満たさない")
            line = f"- {mark}：{k.text}（根拠：{k.evidence}）"
            if k.ok is False and k.fix:
                line += f" → {k.fix}"
            out.append(line)
    out += ["", "出典：DORA AI Capabilities Model（2025）。点は満たした基準の数。測れない基準は点に入れない。"]
    return "\n".join(out) + "\n"
