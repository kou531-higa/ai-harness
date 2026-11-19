# 変更の記録

## 0.2.2（2026-11-19）

運用（非公開のサンプルアプリで4週間）の1週目に見つかった穴を直した。
- 個人情報の担当を中身で足す正規表現が `log.info` に当たらなかった（`\blog(ger)?\.(info|…)` に）
- 決定者マップの役の名前（`@pm` など）が本物の GitHub アカウントへのメンションになりうる。導入時に置き換えるよう書き、判断チケットでは書式つきで書く
- 決まった判断チケットの `needs-decision` を外すと、`harness stats` が決まるまでの日数を数えられない。外さずに閉じる

## 0.2.1（2026-11-19）

- 判断チケットは、AI が `/decision-memo` の手順と型で `gh issue create` して起票してよい（決めるのは人）。CLAUDE.md と feature・bugfix・catalog-challenge・spec-review・verify の書き方を揃えた。運用で、AI が止まって「起票してよいか」と聞き、止まり方が回によって割れた（3回）ため

- `harness doctor`：DORA の AI の7つの能力で、リポジトリを各0〜3点に診断する。点ごとに根拠を出し、確かめられない基準は「測れない」として点に入れない
- `harness stats`：マージした PR の数・リードタイム・行数・修正の PR の割合（DORA の指標の代わり）と、AI が止まった理由・判断待ちの日数・フックで止めた回数を数える。データがないものは「測れない」と書く
- `harness stats --html`：ダッシュボード（1枚の HTML）。週ごとのマージした PR と AI が止まった件数の棒、止まった理由・判断待ち・フックの表。明るい表示と暗い表示に合わせる

## 0.2.0（2026-11-19）

- `harness upgrade`：入れたあとに更新されたテンプレートを取り込む。触っていないファイルは入れ替え、人が直したファイルは上書きせず `<ファイル>.harness-new` に置く。`harness init` は入れたファイルの中身を記録する
- 決まり：`docs/decisions/rules.md`・`/harness-rule`・判断記録の型。決まりで答えが出る論点は人へ戻さない（CLAUDE.md・`/decision-memo`）
- 反証役：`catalog-challenger` と `/catalog-challenge`。`/review` はカタログの変更で反証役も呼ぶ
- PR の行数の検査で、生成物（`*.generated.*`・`*_generated.py`）を数えない。テストは名前が生成物の形でも数える

## 0.1.0（2026-11-18）

- `harness init`・`harness labels`。規約・フック3本・権限・pre-push・`merge_pr.py`
- 仕様の検査（未確定の印・食い違い・未決事項台帳・決定者マップ）と仕様レビュー役
- `/impact`・`/verify`、AI レビュー（場所で選び中身で足す・未カバー）、禁止パターン
