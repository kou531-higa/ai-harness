# 人と話さず動かす（claude -p）とき

台本（シェルや CI）から `claude -p` で AI を動かすときの決まり。
会話で動かすときと違い、途中で人が止められない。だから「何を読ませるか」「どこまで動いてよいか」「いつ終わったとみなすか」を、台本の側ではっきり渡す。

> 旗（`--xxx`）の名前と既定は、Claude Code の版で変わる。使う版の `claude --help` で確かめ、版を固定する。
> 版を上げたら、下の「確かめること」をもう一度流す。

## 1. 読ませるものを明示して渡す

- 将来、`-p` の既定が `--bare` になる予定がある。`--bare` では、CLAUDE.md・フック・スキル・サブエージェント・設定ファイルが自動では読まれない
- 今の版で既定が変わっていなくても、台本では次を明示して渡す。既定が変わっても、同じ動きになるようにするため
  - `--settings .claude/settings.json`（権限とフック。フックが動かないと、守る仕組みが消える）
  - `--agents`（レビュー役などのサブエージェント。ファイルから読まれないときに渡す）
  - `--append-system-prompt "$(cat CLAUDE.md)"`（規約。読まれないときに渡す）
- 台本の最初に、フックが動くか（例：守るファイルの編集が止まるか）を1回確かめる

## 2. 権限モードを明示する

- 権限モードを指定しないと、確認を求めるモードで始まり、人がいないので止まる
- `--permission-mode` で決めて渡す。広げすぎない。編集だけ許すなら `acceptEdits` と、`.claude/settings.json` の `allow` と `deny`
- 確認なしで何でもできるモード（`bypassPermissions`）は、使い捨ての隔てた環境のときだけにする

## 3. 背景の作業を止める（レビューの待ち）

- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` を付けて動かす
- 背景の作業（背景のサブエージェント・背景のコマンド）があると、まとめ役が担当の結果を待たずに終わることがある。`-p` では、待つかどうかがモデルの判断になるため
- `/review` は、レビュー役を前景で動かし、全員の結果がそろってからまとめる。それでも台本の側で、結果（PR のコメントと `.harness/reviews/pr-<番号>.json`）がそろったかを確かめてから次へ進む

## 4. 結果は決めた形で受け取り、上限をかける

- `--output-format json`：台本は AI の文章を読まず、JSON で判定する（終わり方・費用・手数）
- `--json-schema`（使える版なら）：答えの形を決めて、台本がその項目で判定する
- `--max-turns`：1回の実行の手数の上限
- `--max-budget-usd`：1回の実行の費用の上限
- 上限で止まったら、止まったことを記録し、人へ戻す（同じ実行を何度も繰り返さない）

## 5. 終わってよい条件を、フックで強制する

- Stop フック `check-done-on-stop.py` は、変更があるのに検査が通っていなければ、終わりを止める（exit 2）
- 既定では無効。`-p` で動かすときは有効にする（会話で動かすときは、終わるたびに検査が走って重いので、既定では切ってある）
  - `HARNESS_STOP_CHECK=1`：有効にする
  - `HARNESS_STOP_CHECK_CMD="make check"`：走らせる検査（既定は `make check`）
  - `HARNESS_STOP_CHECK_TIMEOUT=600`：秒。超えたら通っていない扱い
- 同じ中身で一度通ったら、走らせ直さない（`.harness/stop-check.json`）。すでに1回止めた後は止めない（終わらない輪にしないため）
- 有効にするのは、台本の環境変数か、`.claude/settings.local.json` の `"env"`

## 6. 例

```
export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
export HARNESS_STOP_CHECK=1

claude -p "/feature #123" \
  --settings .claude/settings.json \
  --permission-mode acceptEdits \
  --output-format json \
  --max-turns 80 \
  --max-budget-usd 5 \
  > .harness/runs/feature-123.json

# 台本は JSON で判定する（例：is_error が false か、上限で止まっていないか）
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(1 if r.get("is_error") else 0)' \
  .harness/runs/feature-123.json
```

並べて動かすときは、`docs/harness/parallel.md` の決まりも守る（fetch は親が1回など）。

## 7. 確かめること（版を上げたら）

- フックが動く（守るファイルの編集が止まる・Stop フックが検査の失敗で止める）
- `/review` が、すべての担当の結果を待ってから PR にコメントする
- `--bare` を付けても、上の旗を渡せば同じ動きになる
