# 変更の記録

## 0.2.0（2026-11-19）

- `harness upgrade`：入れたあとに更新されたテンプレートを取り込む。触っていないファイルは入れ替え、人が直したファイルは上書きせず `<ファイル>.harness-new` に置く。`harness init` は入れたファイルの中身を記録する
- 決まり：`docs/decisions/rules.md`・`/harness-rule`・判断記録の型。決まりで答えが出る論点は人へ戻さない（CLAUDE.md・`/decision-memo`）
- 反証役：`catalog-challenger` と `/catalog-challenge`。`/review` はカタログの変更で反証役も呼ぶ
- PR の行数の検査で、生成物（`*.generated.*`・`*_generated.py`）を数えない。テストは名前が生成物の形でも数える

## 0.1.0（2026-11-18）

- `harness init`・`harness labels`。規約・フック3本・権限・pre-push・`merge_pr.py`
- 仕様の検査（未確定の印・食い違い・未決事項台帳・決定者マップ）と仕様レビュー役
- `/impact`・`/verify`、AI レビュー（場所で選び中身で足す・未カバー）、禁止パターン
