# app-spec-crawler

<p align="center"><img src="assets/hero.png" alt="Web アプリの画面を巡回して撮り、仕様書にまとめる app-spec-crawler のイメージ" width="100%"></p>

**ログイン済みの Web アプリを、読み取り専用で全画面めぐり、スクリーンショット付きの仕様書を作る [Claude Code](https://docs.anthropic.com/en/docs/claude-code) スキル。**

設計書が残っていない社内システム、引き継いだ管理画面、乗り換え前に中身を洗い出したい SaaS ——
「どんな画面があって、何ができて、どんな決まりで動いているか」を、画面を 1 枚ずつ撮りながら調べて文書にします。
データの保存・更新・削除・送信は一切しません。

## できあがるもの

2 種類の文書を、1 つのフォルダ（`book/`）に作ります。ブラウザで開くだけで読め、zip にしてそのまま渡せます。

| 文書 | 読む人 | 中身 |
|---|---|---|
| **システム概要書**（`guide.html`） | 初めて触れる人・発注者・エンジニアでない担当者 | 1 ページの読み物。このシステムでできること / 誰がどう使うか / 画面の地図 / 主な業務の流れ / 機能ごとの説明（画面の画像つき）/ 決まりごと / 用語 / 確認が必要なこと |
| **画面仕様書**（`index.html` ほか） | 開発・保守・移行の担当者 | 画面ごとの仕様を番号付きの仕様項目（`SPEC-p012-03` など）で並べ、根拠のスクリーンショットにリンク。アプリ共通の仕様 → 階層（URL のディレクトリ）ごとの仕様 → 画面ごとの仕様 → 画面キャプチャ の 4 層 |

- 仕様項目にはそれぞれ「確認済 / 推定 / 要確認」の確かさが付きます。押していないボタンの結果などは「推定」として区別します。
- 左に常設の目次、上の帯で 2 つの文書を切り替え。スマホ幅でも読めます。
- 画面はライト固定です（OS がダークモードでも明るいまま）。

## しくみ

```
 ① crawl     利用者の Chrome（ログイン済み）に browser-use でつなぎ、
             URL を開くだけで全画面をめぐって、全体のスクリーンショットと画面の構造を記録する
 ② describe  Claude がスクリーンショットを 1 枚ずつ見て、画面ごとの仕様を書く（descriptions.json）
 ③ build     画面仕様書（HTML）を組み立てる
 ④ write     claude -p で Claude（Fable 5.1）が、画面仕様書を材料にシステム概要書を書く
 ⑤ verify    できた文書を browser-use で開き、はみ出し・壊れた画像・書き漏れを確かめる
```

巡回と組み立ては決まった処理（プログラム）で、毎回同じ結果になります。
AI が受け持つのは「各画面の意味を読み解いて書く」②と④だけです。

## 安全のための決まり

対象は本番環境であることが多いため、読み取り専用を何重にも守ります。

- 画面は **URL で開くだけ**。入力・送信・保存・削除はしない。クリックするのは同じページ内のタブ（`#xxx` へのリンク）だけ。
- `logout` `delete` `approve` `export` などを含む URL は開かない。ボタンの文字に「保存」「削除」「承認」などがあれば押さない（`scripts/safety_rules.json` で調整できる）。
- ログイン切れを見つけたら止まり、人にログインし直してもらってから続きを回す。
- 利用者の開いているタブには触らず、作業用のタブを 1 つ作って回す。
- 詳しくは [`references/safety-policy.md`](references/safety-policy.md)。

## インストール

### Claude Code に貼るだけ（おすすめ）

Claude Code を開いて、次の文をそのまま貼ってください。Claude が入れて、使えるかどうかまで確かめます。

```text
Claude Code のスキル app-spec-crawler をインストールしてください。

1. git clone https://github.com/akkijp/app-spec-crawler-skill.git ~/.claude/skills/app-spec-crawler
   （フォルダ名は app-spec-crawler にする。既にあれば上書きせず、私に聞く）
2. mkdir -p ~/.local/bin && ln -sf ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler
   ~/.local/bin が PATH に無ければ、通し方を教えて。
3. app-spec-crawler doctor を実行して、結果の表をそのまま見せて。
4. NG があれば、何に必要で、どう直すかを説明して。パッケージのインストールなど直す操作は、私が承認してから行って。
   Chrome の設定のように私が操作するものは、手順を示して待って。
5. 最後に app-spec-crawler help の内容を見せて。
```

### 手で入れる

```bash
git clone https://github.com/akkijp/app-spec-crawler-skill.git ~/.claude/skills/app-spec-crawler
mkdir -p ~/.local/bin
ln -sf ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler
app-spec-crawler doctor          # 足りないものと直し方が出る
```

更新は `cd ~/.claude/skills/app-spec-crawler && git pull`。

## 必要なもの

| もの | 用途 | 入れ方 |
|---|---|---|
| macOS | Chrome とのつなぎ方の確認が macOS 向け | — |
| Google Chrome | 対象アプリにログインしておくブラウザ | — |
| Chrome の遠隔デバッグの許可 | browser-use が Chrome につなぐため | Chrome で `chrome://inspect/#remote-debugging` を開き「Allow remote debugging for this browser instance」を有効にする（初回、つないだときに Chrome に確認が出る） |
| [browser-use](https://github.com/browser-use/browser-use) | 巡回と見た目の確認 | `uv tool install browser-use`（uv が無ければ `brew install uv`） |
| Python 3.9 以上 | コマンド本体（標準ライブラリのみ） | macOS 標準のもので可 |
| Claude Code（`claude` コマンド、ログイン済み） | ② と ④（④ は `claude -p` を呼ぶ） | [公式の手順](https://docs.anthropic.com/en/docs/claude-code) |
| zip（任意） | できた文書を渡すとき | macOS 標準 |

Playwright は不要です（Playwright 方式の巡回 `scripts/crawl.py` を明示して使うときだけ要ります）。
browser-use が使えない環境では、Claude の computer-use で画面を見ながら手で回す手順もあります（[`references/manual-crawl.md`](references/manual-crawl.md)）。

`app-spec-crawler doctor` はこれらを 1 つずつ確かめ、足りないものがあれば「何に要るか」と「直し方」を出します。

## 使い方

### Claude に頼む

対象アプリに Chrome でログインしておき、Claude Code にこう頼みます。

```text
https://app.example.com/admin/ 以下を巡回して、仕様書を作って
```

Claude が `doctor` → `crawl` → 画面ごとの説明 → `build` → `write` → `verify` まで進め、できた文書の場所を返します。
`/app-spec-crawler` だけを打つと使い方が出ます。

### コマンド

| コマンド | すること |
|---|---|
| `app-spec-crawler` / `help` | 使い方を出す |
| `app-spec-crawler doctor [--url URL]` | 今使えるかを表で出す。`--url` を付けると、そのアプリのタブが開いているかも見る |
| `app-spec-crawler crawl --url URL --out DIR` | 巡回する（`DIR/pages.json` と `DIR/screenshots/`） |
| `app-spec-crawler describe DIR` | 画面ごとの説明を書くための雛形 `DIR/descriptions.json` を作る |
| `app-spec-crawler build DIR` | 画面仕様書 `DIR/book/` を作る |
| `app-spec-crawler write DIR` | システム概要書 `DIR/book/guide.html` を書く（数分。`--budget` で費用の上限、既定 8 ドル） |
| `app-spec-crawler verify DIR` | 文書を開いて、幅 1440px / 390px で撮って確かめる（`DIR/verify/`） |

`crawl` のおもなオプション:

| オプション | 意味 |
|---|---|
| `--resume` | 途中で止まった巡回の続き。ログインし直して URL が変わっても続きから回る |
| `--scope-prefix URL` | この文字列で始まる URL だけ回す（既定: 起点と同じオリジン） |
| `--route-param NAME` | 画面を `?NAME=...` で切り替えるアプリで、その値を画面の住所として扱う |
| `--variant-param NAME` | 別の画面として扱うクエリ（複数可） |
| `--exclude REGEX` | 開かない URL（複数可） |
| `--allow-route PATH` | 危険な言葉を含んでも開いてよい画面（複数可） |
| `--hide SELECTOR` | 撮る前に隠す重なり（サイト内ヘルプ・チャット窓などの CSS セレクタ。複数可） |
| `--max-pages N` | 上限の画面数（既定 300） |

### エラーのとき

失敗すると「✖ エラー / 原因 / 直し方」の 3 段で出ます。直し方にパッケージのインストールなどが含まれるとき、Claude は承認をもらってから実行します。

| 終了コード | 意味 |
|---|---|
| 0 | 成功 |
| 2 | 使い方の誤り |
| 3 | ログイン切れ（ログインし直して `--resume`） |
| 4 | Chrome につながらない |
| 5 | 必要なものが入っていない |
| 6 | 見た目の確認で問題あり |
| 7 | 画面仕様書の生成に失敗 |
| 8 | システム概要書の書き出しに失敗 |
| 1 | その他 |

## 注意

- **できるのは「見える範囲」の仕様です。** スクリーンショットと画面の構造から読み取った推定を含みます。「推定」「要確認」の項目は、原本の設計書や開発者に確かめてください。
- **スクリーンショットには実データが写ります。** 顧客名・従業員名などが写るので、できた文書の扱い（共有先・保存先）に気を付けてください。
- **④ write は Claude の利用料がかかります**（`claude -p` を 1 回呼ぶ。`--budget` で上限を決められる）。
- ログインの有効期限が短いアプリでは、途中でログイン切れになることがあります。ログインし直して `--resume` で続きから回せます。

## フォルダ構成

```
app-spec-crawler/
├── SKILL.md                 Claude が読む手順書
├── bin/app-spec-crawler     コマンドの入口
├── scripts/
│   ├── app_spec_crawler.py  コマンド本体（help / doctor / crawl / describe / build / write / verify）
│   ├── bu_crawl.py          browser-use の中で動く巡回
│   ├── bu_verify.py         browser-use の中で動く見た目の確認
│   ├── build_book.py        画面仕様書の組み立て
│   ├── safety_rules.json    押さない・開かない言葉の一覧
│   └── crawl.py             （任意）Playwright 方式の巡回
├── references/
│   ├── safety-policy.md     安全のための決まりの詳細
│   ├── description-guide.md 画面ごとの説明の書き方
│   ├── guide-prompt.md      システム概要書を書かせる指示
│   └── manual-crawl.md      browser-use の注意・computer-use で手で回す手順
└── assets/book.css          文書の見た目
```
