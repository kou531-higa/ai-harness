---
name: spec-review
description: 仕様の下書きを、実装の前に仕様レビュー役（別のコンテキストの AI）に読ませ、未確定と食い違いを台帳に載せて、人に聞くことを並べる
argument-hint: "仕様のパス（例：docs/specs/SPEC-010-partner-d.md）"
disable-model-invocation: true
---

# /spec-review：仕様のレビュー

仕様：$ARGUMENTS

## 手順

1. **機械で数える**：
   ```
   python3 scripts/check_undecided.py $ARGUMENTS
   python3 scripts/check_spec_consistency.py docs/specs --baseline docs/specs/consistency-baseline.json
   ```
2. **別の目で読む**：サブエージェント `spec-reviewer` に、仕様のパスだけを渡してレビューさせる。
   自分の考えや答えの候補は渡さない（引きずられるため）。
3. **合わせる**：1 と 2 の結果を1つの表にする。同じものは1件にまとめ、どちらで見つかったかを書く。
4. **台帳を作り直す**：`python3 scripts/undecided_ledger.py`。印のない未確定（「など」「適宜」）は台帳に載らないので、
   仕様の該当の行に「要確認」と印を付けてよいか人に聞く。
5. **人に返す**：表と、決定者ごとの質問の一覧を出す。決定者ごとに、`/decision-memo` の手順と型で判断チケットを起票する（起票はしてよい。決めるのは人）。

## 終わってよい条件

- 1 と 2 の両方を実行し、合わせた表がある
- 1件ごとに場所と、誰に何を聞くかが書いてある
- 未決事項台帳が作り直してある（`python3 scripts/undecided_ledger.py --check` が通る）

## 止まって人へ戻す条件

- 未確定や食い違いが1件でもある → 実装に進まない。表を返して止まる（`ai-stop:spec-undecided` または `ai-stop:spec-conflict`）
- 仕様レビュー役が「未カバー」を返した → その範囲を人に伝える
