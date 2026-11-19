# api/ の規約（API：NestJS・TypeORM・TypeScript）

このディレクトリのファイルを触るときに読み込まれる。全体の規約はリポジトリ直下の CLAUDE.md。

## 書き方
- モジュールは業務の単位で分ける。controller は薄く（入力の受け取りと返却だけ）、業務の処理は service に書く
- 部品の組み立ては NestJS の DI だけ。`new` で依存を作らない
- 入力は DTO と class-validator で検査する。検査を service の中で手書きしない
- エラーは共通の例外（`src/common/errors/`）を投げ、返し方は共通の例外フィルタに任せる
- ログは共通のロガーだけ。`console.log` を使わない。**個人情報（氏名・電話番号・住所・メール）をログに出さない**
- DB は TypeORM。SQL の組み立てとページングは共通の土台（`src/common/db/`）を使う。生の SQL を文字列でつながない
- 更新が複数の表にまたがるときは、共通のトランザクションの仕組みを使う
- 状態の判定（「請求の対象か」など）は `src/common/catalog/`（カタログから作ったもの）を使う。`where status = '...'` を直接書かない
- API には Swagger の説明を付ける

## テスト
- 単体テストは Jest（`*.spec.ts`）。`@nestjs/testing` で組み立て、DB は共通のテストの土台を使う
- API を HTTP で呼ぶテストは supertest（`test/`）

## 止まって人へ戻す
- 共通部品（`src/common/`）やカタログを変える必要がある → `ai-stop:shared-component`
- 応答の形（項目名・型）を、既存の利用者に影響する形で変える → `ai-stop:customer-agreement`
