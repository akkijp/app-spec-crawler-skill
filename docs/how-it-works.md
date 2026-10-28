# しくみ

[← README に戻る](../README.md)

## 流れ

```
 ① crawl     利用者の Chrome（ログイン済み）に browser-use でつなぎ、
             URL を開くだけで全画面をめぐって、全体のスクリーンショットと画面の構造を記録する
 ② describe  Claude がスクリーンショットを 1 枚ずつ見て、画面ごとの仕様を書く（descriptions.json）
 ③ build     画面仕様書（HTML）を組み立てる
 ④ write     claude -p で Claude（Fable 5.1）が、画面仕様書を材料にシステム概要書を書く
 ⑤ verify    できた文書を browser-use で開き、はみ出し・壊れた画像・書き漏れを確かめる
```

巡回と組み立ては決まった処理（プログラム）で、毎回同じ結果になります。AI が受け持つのは、各画面の意味を読み解いて書く ② と ④ だけです。

## できあがる文書

| 文書 | 読む人 | 中身 |
|---|---|---|
| システム概要書（`guide.html`） | 初めて触れる人・発注者・エンジニアでない担当者 | 1 ページの読み物。できること / 誰がどう使うか / 画面の地図 / 主な業務の流れ / 機能ごとの説明（画面の画像つき）/ 決まりごと / 用語 / 確認が必要なこと |
| 画面仕様書（`index.html` ほか） | 開発・保守・移行の担当者 | アプリ共通の仕様 → 階層（URL のディレクトリ）ごとの仕様 → 画面ごとの仕様 → 画面キャプチャ の 4 層 |

- 仕様項目には番号（`SPEC-p012-03` など）と、確かさ（確認済 / 推定 / 要確認）が付き、根拠のスクリーンショットにリンクします。
- 上の帯で 2 つの文書を切り替えます。画面仕様書は左に常設の目次があり、スマホ幅でも読めます。
- 画面はライト固定です（OS がダークモードでも明るいまま）。

## 安全のための決まり

- 画面は URL で開くだけ。入力・送信・保存・削除はしない。クリックするのは同じページ内のタブ（`#xxx` へのリンク）だけ。
- `logout` `delete` `approve` `export` などを含む URL は開かない。ボタンの文字に「保存」「削除」「承認」などがあれば押さない（[`scripts/safety_rules.json`](../scripts/safety_rules.json) で調整できる）。
- ログイン切れを見つけたら止まり、人にログインし直してもらってから続きを回す。
- 利用者が開いているタブには触らず、作業用のタブを 1 つ作って回す。

詳しくは [`references/safety-policy.md`](../references/safety-policy.md)。

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
├── docs/                    このページなど、README の詳細
└── assets/                  文書の見た目（book.css）と README の画像
```
