"""GitHub のラベル。AI が止まった理由（ai-stop:*）を数えるために使う。"""

from __future__ import annotations

from typing import List, Tuple

# (名前, 色, 説明)。理由の一覧は CLAUDE.md の「人へ戻す」と揃える
LABELS: List[Tuple[str, str, str]] = [
    ("needs-decision", "d93f0b", "人の判断を待っている"),
    ("size-exception", "fbca04", "PR の行数の上限を超えてよいと人が認めた"),
    ("owner-approved", "0e8a16", "型の設定などを変える PR を、オーナーが中身を見て認めた（AI は付けない）"),
    ("owner-digest", "5319e7", "型を回す AI が作る、オーナーへの1日1枚の確認"),
    ("ai-stop:spec-undecided", "c5def5", "仕様に未確定がある"),
    ("ai-stop:spec-conflict", "c5def5", "仕様どうし、または仕様と実装が食い違う"),
    ("ai-stop:customer-agreement", "c5def5", "顧客の合意が要る"),
    ("ai-stop:two-failures", "c5def5", "同じ失敗が2回続いた"),
    ("ai-stop:shared-component", "c5def5", "共通部品・カタログ・DB の構造を変える"),
    ("ai-stop:pr-too-large", "c5def5", "PR が大きすぎる"),
    ("ai-stop:irreversible", "c5def5", "元に戻せない操作"),
    ("ai-stop:security", "c5def5", "セキュリティ・個人情報"),
    ("ai-stop:uncovered", "c5def5", "検査やレビューが届かない箇所"),
    ("ai-stop:other", "c5def5", "そのほか"),
]


def gh_commands(repo: str = "") -> List[List[str]]:
    """ラベルを作る（あれば上書きする）gh のコマンド。"""
    cmds = []
    for name, color, desc in LABELS:
        cmd = ["gh", "label", "create", name, "--color", color, "--description", desc, "--force"]
        if repo:
            cmd += ["--repo", repo]
        cmds.append(cmd)
    return cmds
