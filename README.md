# ai-harness

**AIは作業し、人は判断する。** その工程を、リポジトリに置ける形（ハーネス）にするためのテンプレートとCLIです。

> 状態：作成中（P1）。

## 何をするものか

Claude Code を「個人が使う道具」ではなく、チームの開発工程に組み込むための仕組みです。

| 仕組み | 役割 |
|---|---|
| CLAUDE.md | AIと人の共通の規約（短く保つ） |
| 権限とフック | 禁止する操作を、お願いではなく設定で止める |
| スキル | `/feature`、`/bugfix` など、手順を呼び出せる形にする |
| レビュー担当AI | 別のコンテキストで、変更パスごとにレビューする |
| 品質ゲート | テスト・Lint・型・差分カバレッジ・PRサイズを毎回確かめる |
| 判断メモ | AIが止まったときに、人が速く決められる形で戻す |
| 指標 | AIが止まった理由とDORA指標を数え、ルールに変える |

## 使い方

```
# 導入先のリポジトリで実行する（既にあるファイルは上書きしない）
uvx --from git+https://github.com/kou531-higa/ai-harness harness init --dry-run
uvx --from git+https://github.com/kou531-higa/ai-harness harness init
uvx --from git+https://github.com/kou531-higa/ai-harness harness labels   # AI が止まった理由のラベル
```

テンプレートが更新されたら、導入先で `harness upgrade` を実行します。

```
uvx --from git+https://github.com/kou531-higa/ai-harness harness upgrade --dry-run
uvx --from git+https://github.com/kou531-higa/ai-harness harness upgrade
```

- 入れたまま触っていないファイルは、新しいテンプレートに入れ替えます
- 人が直したファイル（`CLAUDE.md` など）は上書きせず、新しいテンプレートを `<ファイル>.harness-new` に置きます。差分を見て手で合わせ、`.harness-new` を消します
- 人が消したファイルは戻しません。テンプレートから消えたファイルは、知らせるだけです

- 層（`web`・`api`・`batch`・`db`・`e2e`）は、ディレクトリがあるものだけ規約を入れます
- main への直接の push を止める pre-push フックと、検査がすべて緑のときだけマージする `scripts/merge_pr.py` が入ります（ブランチ保護が使えない無料プランの非公開リポジトリ向け）

## 予定

- **P1**：フック3本、スキル3つ、仕様の未確定の検査、PRチェック、サンプルアプリ `demo-shop`
- **P2**：AIレビュー、`harness doctor`（7観点の診断）、`harness stats`（指標）、4週間の運用記録
- **P3**：IaC、デプロイとロールバック、SLOアラーム、障害対応
- **P4**：GitLab CI、Bedrock、Jira / Backlog への対応

## このリポジトリについて

- サンプルデータは、すべて架空のものです。
- 現在、外部からの Pull Request は受け付けていません（[CONTRIBUTING.md](CONTRIBUTING.md)）。

## ライセンス

[MIT](LICENSE)
