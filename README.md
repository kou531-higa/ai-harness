# ai-harness

**AIは作業し、人は判断する。** その工程を、リポジトリに置ける形（ハーネス）にするためのテンプレートとCLIです。

> 状態：0.2.4。P1（仕組みの一式と、サンプルアプリでの検証）まで。変更の記録は [CHANGELOG.md](CHANGELOG.md)。

## 何が入るか

`harness init` で、導入先のリポジトリに次のものが入ります（層の規約は、そのディレクトリがあるものだけ）。

| 分類 | 入るもの | 役割 |
|---|---|---|
| 規約 | `CLAUDE.md`（150行以内）と層ごとの `CLAUDE.md`（web・api・batch・db・e2e） | AI と人の共通の約束。「決めないこと（人へ戻す）」と、止まるときの理由（`ai-stop:*`）を決める |
| 止める設定 | `.claude/settings.json`、フック4本（`protect-paths`・`format-and-lint`・`check-specs-on-stop`・`check-done-on-stop`）、pre-push、`scripts/merge_pr.py` | 消してはいけないファイルの編集、main への直接の push と禁止パターンの push、検査が緑でない・判断待ちの PR のマージを、お願いではなく仕組みで止める。`check-done-on-stop`（検査が通るまで終えない）は既定で無効 |
| 仕様 | `scripts/check_undecided.py`（未確定の5つの印）・`check_spec_consistency.py`（仕様どうしの食い違い）・`undecided_ledger.py`（未決事項台帳）・`docs/decisions/owners.md`（決定者マップ）・仕様レビュー役 | 決まっていないことを AI に推測で埋めさせず、誰に何を聞くかまで返させる |
| スキル | `/feature` `/bugfix` `/decision-memo` `/spec-review` `/impact` `/verify` `/review` `/catalog-challenge` `/harness-rule` | 手順を呼び出せる形にする。どれも「終わってよい条件」と「止まって人へ戻す条件」を持つ |
| レビュー | `scripts/review_route.py`・`.claude/review-routes.json`・担当ごとの観点（`.claude/review/`）・レビュー役 | 変更の場所で担当を選び、中身（個人情報・状態名など）で足す。見ていない所は「未カバー」と必ず書かせる |
| 判定の正本 | `scripts/check_forbidden.py`・`.claude/forbidden-patterns.json`・反証役（`catalog-challenger`） | 状態名を並べた判定などを、追加した行だけで止める。状態定義カタログの変更は、別の AI にわざと崩させる |
| 決まり | `docs/decisions/rules.md`・`/harness-rule`・判断記録の型（なぜ・合意した範囲・先送り・根拠） | 一度決めた判断の基準を決まりにし、次の同じ種類の判断は人に戻さない。決まりには「当てはまらない場合」を必ず書く |
| PR | `scripts/check_pr_size.py`（本体400行・テスト800行）・`scripts/check_dec_refs.py`（参照した DEC があるか）・PR テンプレート・`.github/workflows/`（PR の検査と毎晩の仕様の検査） | 1PR＝1チケット。「関係する DEC」「人が判断すべき点」と「証拠」を必ず書かせる |

## 検証の結果（非公開のサンプルアプリで）

架空の業務アプリ（設備の保守受付）に、未確定・食い違い・欠陥を件数を決めて仕込み、同じ依頼を **素の Claude Code** と **ハーネスあり** で各3回実行して比べました（モデルは同じ。採点は作者1人）。

| 確かめたこと | 素 | ハーネスあり |
|---|---|---|
| 未確定が残る仕様で「実装して」と頼んだとき、実装の前に止まった | 0/3 | 3/3（未決事項台帳がなくても 3/3） |
| 未確定を聞かずに自分で決めた件数 | 平均2件 | 0件 |
| 経緯の分からない請求の条件を、聞く前に消した | 3/3 | 0/3 |
| 変える前に、今の振る舞いを固定するテストを書いた | 0/3 | 3/3 |
| PR に仕込んだ欠陥6件の検出 | 6/6 | 6/6（差なし） |
| 見ていない所を「未カバー」と明示した | 0/3 | 3/3 |
| 決まりがあるとき、次の取引先の追加で人に来た判断（6件中） | 6件（決まりなし） | 3件（決まりあり。広げすぎ0件） |

- 差が出たのは「止まる・勝手に埋めない・決まりにすると人に来る判断が減る」。**見つける数と、合格基準の合否には差が出ませんでした**
- ハーネスありは、レビューで費用が約3倍、実装で約1.3倍かかります
- 仕込みが甘くて AI に指摘された所は直してから回し直し、直す前の結果も残しています

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

今のリポジトリが、AI の効果を引き出す土台をどれだけ持っているかを診断します（DORA の AI の7つの能力。各0〜3点、根拠つき）。

```
uvx --from git+https://github.com/kou531-higa/ai-harness harness doctor --out doctor.md
uvx --from git+https://github.com/kou531-higa/ai-harness harness stats --since 28 --html docs/metrics/index.html   # 届ける力とハーネスの指標（PR・Issue・フックの記録から）。--html でダッシュボード
```

- 層（`web`・`api`・`batch`・`db`・`e2e`）は、ディレクトリがあるものだけ規約を入れます
- main への直接の push を止める pre-push フックと、検査がすべて緑のときだけマージする `scripts/merge_pr.py` が入ります（ブランチ保護が使えない無料プランの非公開リポジトリ向け）

## 人と話さず動かす（claude -p）とき

台本や CI から `claude -p` で動かすときは、読ませるもの・権限・終わり方を台本の側で明示します。詳しくは、入れた先の `docs/harness/headless.md`。

- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` を付ける（まとめ役が、担当の結果を待たずに終わらないように）
- 権限モードを `--permission-mode` で明示する（指定しないと確認を求めて止まる）
- `--settings .claude/settings.json` など、設定・フック・サブエージェントを明示して渡す（将来 `--bare` が既定になり、自動では読まれなくなる予定のため）
- 結果は `--output-format json` で受け取り、`--max-turns`・`--max-budget-usd` で上限をかける
- Stop フック `check-done-on-stop` を `HARNESS_STOP_CHECK=1` で有効にし、検査（既定は `make check`）が通るまで終わらせない

作業場所（git worktree）を分けて並べるときの決まり（fetch は親が1回・自分のブランチ名で絞る・ポートを `.env` でずらす・マージは1本ずつ）は `docs/harness/parallel.md` にあります。

## 予定

- **P1（済み）**：上の一式、`harness upgrade`、サンプルアプリでの検証
- **P2**：`harness doctor`・`harness stats`・ダッシュボード（済み）、4週間の運用記録
- **P3**：IaC、デプロイとロールバック、SLOアラーム、障害対応
- **P4**：GitLab CI、Bedrock、Jira / Backlog への対応

## このリポジトリについて

- サンプルデータは、すべて架空のものです。
- 現在、外部からの Pull Request は受け付けていません（[CONTRIBUTING.md](CONTRIBUTING.md)）。

## ライセンス

[MIT](LICENSE)
