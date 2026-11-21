---
name: catalog-challenge
description: 状態定義カタログ（catalog/）の変更を、別のコンテキストの反証役に崩させる。異議があれば判断チケットにして人へ戻す。手元の Claude Code で動かす
argument-hint: "PR の番号、または比べる先（例：origin/main）"
disable-model-invocation: true
---

# /catalog-challenge：カタログの変更への反証

対象：$ARGUMENTS

カタログは全部の層の判定の正本なので、変えるときは「書いた人とは別の目で、わざと崩す」を必ず通す。
`/review` は、変更に `catalog/` が含まれるとき、この手順の 2〜4 も行う。

## 手順

1. **基準を決める**：PR の番号なら `gh pr checkout <番号>` し、基準は `origin/<baseRefName>`。比べる先が渡されたら、それを基準にする。
   この会話でカタログの変更を書いていたなら、`/clear` してから始める（書いた考えに引きずられるため）。
2. **材料を集める**：
   - `git diff <基準>...HEAD -- catalog/`。差分がなければ「カタログの変更なし」と書いて終わる
   - 差分に出てくる状態名を集め、`python3 scripts/impact.py <状態名…>` で、状態名を使っている所を一覧にする
   - 変更の理由：PR の本文・関係するチケット・`docs/decisions/` の判断の記録
3. **崩させる**：サブエージェント `catalog-challenger` を起動し、2 の材料だけを渡す。変更を書いた人の説明（なぜ良いと思ったか）は渡さない。
4. **まとめる**：反証役の結果をそのまま載せ、異議ごとに「決める人」を決定者マップ（`docs/decisions/owners.md`）で確かめる。
5. **人へ戻す**：異議が1件でもあれば、`/decision-memo` の手順と型で判断チケットを `gh issue create` で起票し、PR に `needs-decision` を付ける（下の表）。異議がなければ「異議なし」と、崩せなかった観点を PR にコメントする。
6. **記録する**：`.harness/reviews/catalog-<番号または基準>.json` に、異議の件数と種類・未カバーの件数を書く。

## 終わってよい条件

- 反証役が結果を返し、崩し方ごとの結果と未カバーが書いてある
- 異議があれば判断チケットがあり、PR に `needs-decision` が付いている
- `.harness/reviews/catalog-*.json` がある

## 止まって人へ戻す条件

| 状況 | 理由 |
|---|---|
| 新しい状態が既存の状態と重なる・ほかの正本と食い違う | `spec-conflict` |
| 判定（取り消せるかなど）に入るかが決まっていない | `spec-undecided` |
| 業務の扱いや顧客との約束が変わる | `customer-agreement` |
| すでにある依頼やデータの扱いが要る | `irreversible` |
| 反証役が重要な所を確かめられなかった | `uncovered` |

## してはいけないこと

- 反証の中でカタログや生成物を直す（直すのは人の決定のあと、別の作業）
- 異議を「軽い」として自分で落とす。落とすかは人が決める
