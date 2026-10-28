# app-spec-crawler

<p align="center"><img src="assets/hero.png" alt="Web アプリの画面を巡回して撮り、仕様書にまとめる app-spec-crawler のイメージ" width="100%"></p>

**ログイン済みの Web アプリを読み取り専用で全画面めぐり、スクリーンショット付きの仕様書を作る [Claude Code](https://docs.anthropic.com/en/docs/claude-code) スキル。**

設計書の無い社内システムや、引き継いだ管理画面の中身を洗い出すときに使います。データの保存・更新・削除・送信は一切しません。

## できあがるもの

- **システム概要書** … 初めての人向けの 1 ページ。できること・画面の地図・業務の流れ・決まりごと
- **画面仕様書** … 画面ごとの仕様と、根拠のスクリーンショット

どちらも HTML で、ブラウザで開くだけで読めます。

## インストール

Claude Code に次の文を貼ってください。Claude が入れて、使えるかどうかまで確かめます。

```text
Claude Code のスキル app-spec-crawler をインストールしてください。

1. git clone https://github.com/akkijp/app-spec-crawler-skill.git ~/.claude/skills/app-spec-crawler
   （既にあれば上書きせず、私に聞く）
2. mkdir -p ~/.local/bin && ln -sf ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler
3. app-spec-crawler doctor を実行して、結果をそのまま見せて。
4. NG があれば理由と直し方を説明して。インストールなど直す操作は、私が承認してから行って。
```

必要なもの: macOS・Google Chrome・[browser-use](https://github.com/browser-use/browser-use)・Claude Code。詳しくは [docs/install.md](docs/install.md)。

## 使い方

1. 対象のアプリに Chrome でログインしておく
2. Claude Code に頼む

```text
https://app.example.com/admin/ 以下を巡回して、仕様書を作って
```

巡回 → 画面ごとの説明 → 仕様書の作成 → 見た目の確認まで Claude が進め、できた文書の場所を返します。

## もっと詳しく

- [インストールと必要なもの](docs/install.md)
- [使い方の詳細](docs/usage.md) — コマンド、オプション、エラーのとき、注意
- [しくみ](docs/how-it-works.md) — 処理の流れ、できあがる文書、安全のための決まり

## ライセンス

[MIT](LICENSE)
