# web/ の規約（画面：Next.js・React・TypeScript）

このディレクトリのファイルを触るときに読み込まれる。全体の規約はリポジトリ直下の CLAUDE.md。

## 書き方
- 画面は App Router（`src/app/`）。データの取得と状態は Redux Toolkit の slice にまとめ、画面の部品には業務の判定を書かない
- API の呼び出しは共通の `src/lib/api/`（axios のクライアント）だけを使う。`fetch` や axios を直接呼ばない
- 入力の画面は react-hook-form と、共通の入力部品を使う。チェックの文言は共通の定義に合わせる
- 一覧は共通の表とページングの部品を使う。ページングを自分で作らない
- 状態の表示名や色、判定は `src/lib/catalog/`（カタログから作ったもの）を使う。状態の値を直接書かない
- 見た目は Tailwind CSS。新しい共通部品を作ったら Storybook のストーリーも足す

## テスト
- 単体テストは Vitest と Testing Library（`src/__tests__/`）。役割（role）か `data-testid` で要素を取る
- 画面のテストは `e2e/`。testid は `画面-要素`（例：`request-list-filter`）の形にする

## 止まって人へ戻す
- 共通部品（`src/lib/`）を変える必要がある → `ai-stop:shared-component`
- 画面の項目・並び・文言を、仕様にない形で変える必要がある → `ai-stop:spec-undecided`
