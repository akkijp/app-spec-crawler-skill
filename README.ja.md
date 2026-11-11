<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/readme/banner-dark.png" />
    <img src="docs/readme/banner-light.png" width="800" alt="app-spec-crawler: どんな Web アプリも仕様書に" />
  </picture>
</p>

<p align="center">
  <strong>ログイン済みの Web アプリを Claude Code に見せると、全画面をスクリーンショット付きの仕様書にします。読み取り専用です。</strong>
</p>

<p align="center">
  <a href="https://github.com/akkijp/app-spec-crawler-skill/stargazers"><picture><source media="(max-width: 767px)" srcset="https://img.shields.io/github/stars/akkijp/app-spec-crawler-skill?style=flat-square&labelColor=0F1320&logo=github&logoColor=white&color=4F6BFF" /><img alt="GitHub stars" src="https://img.shields.io/github/stars/akkijp/app-spec-crawler-skill?style=for-the-badge&labelColor=0F1320&logo=github&logoColor=white&color=4F6BFF" /></picture></a>
  <a href="LICENSE"><picture><source media="(max-width: 767px)" srcset="https://img.shields.io/badge/license-MIT-4F6BFF?style=flat-square&labelColor=0F1320" /><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-4F6BFF?style=for-the-badge&labelColor=0F1320" /></picture></a>
  <a href="https://docs.anthropic.com/en/docs/claude-code"><picture><source media="(max-width: 767px)" srcset="https://img.shields.io/badge/Claude_Code-skill-D97757?style=flat-square&labelColor=0F1320" /><img alt="Claude Code skill" src="https://img.shields.io/badge/Claude_Code-skill-D97757?style=for-the-badge&labelColor=0F1320" /></picture></a>
  <br />
  <a href="#読み取り専用"><picture><source media="(max-width: 767px)" srcset="https://img.shields.io/badge/crawl-read--only-12A15F?style=flat-square&labelColor=0F1320" /><img alt="Read-only" src="https://img.shields.io/badge/crawl-read--only-12A15F?style=for-the-badge&labelColor=0F1320" /></picture></a>
  <a href="docs/ja/usage.md"><picture><source media="(max-width: 767px)" srcset="https://img.shields.io/badge/docs-en_·_ja_·_zh_·_es_·_ko-5B6B9A?style=flat-square&labelColor=0F1320" /><img alt="Documents in 5 languages" src="https://img.shields.io/badge/docs-en_·_ja_·_zh_·_es_·_ko-5B6B9A?style=for-the-badge&labelColor=0F1320" /></picture></a>
</p>

<p align="center"><a href="README.md">English</a> · <b>日本語</b></p>

https://github.com/user-attachments/assets/0f28552f-e581-4f41-b838-a610962fed5f

<p align="center"><sub>WordPress の見本を前に回したときの記録です（51 画面・仕様 381 項目）。音が出ます。</sub></p>

設計書の無い管理画面を引き継いだのが、作ったきっかけです。この [Claude Code](https://docs.anthropic.com/en/docs/claude-code) スキルは、あなたのログイン済みの Chrome で全画面をめぐり、1 画面ずつ全体を撮って、Claude が文書を書きます。

## <img src="docs/readme/ui/icon-for.png" width="32" height="32" align="absmiddle" alt="" /> こういうときに

- 設計書の無い社内システムの中身を洗い出す
- SaaS を乗り換える前に、今使っている画面と機能を書き出す
- 新しく入った人に「このシステムは何をするものか」を渡す

## <img src="docs/readme/ui/icon-what.png" width="32" height="32" align="absmiddle" alt="" /> できあがるもの

- **システム概要書** … 初めての人向けの 1 ページ。できること・画面の地図・業務の流れ・決まりごと
- **画面仕様書** … 画面ごとの番号付きの仕様項目。各項目に「確認済」「推定」「要確認」の別と、根拠のスクリーンショットへのリンクが付きます

どちらも HTML です。ブラウザで開くだけで読め、zip にして渡せます。

**[実物を見る →](https://akkijp.github.io/app-spec-crawler-examples/)** WordPress の管理画面を回した見本です（英語。50 画面・仕様 376 項目。手で書いたものはありません）。

文書は、Claude と話している言語で書かれます。対応は英語・日本語・中国語（簡体字）・スペイン語・韓国語の 5 つで、それ以外の言語では枠が英語になります。中国語・スペイン語・韓国語の言い回しは機械翻訳です。直しを歓迎します。

## <img src="docs/readme/ui/icon-safe.png" width="32" height="32" align="absmiddle" alt="" /> 読み取り専用

画面を URL で開いて、見るだけです。入力欄に文字を打つ処理も、フォームを送る処理も、コードにありません。

- 保存・削除・承認・送信などのボタンは押しません。クリックするのはページ内のタブだけです。
- `logout` `delete` `approve` `export` などを含む URL は開きません。
- 偽造防止の符号（`_wpnonce` `csrf_token` `authenticity_token` など）が付いたリンクと、読むだけと分かっていない操作のパラメータが付いたリンクは開きません。WordPress の「ゴミ箱へ移動」「有効化」のように、リンクを開くだけでデータが変わるアプリがあり、その見分けに使っています。
- 開かないと決めた URL は、理由つきで `safety_report.json` に残ります。

**道具の側からは分からないこと**: 画面を開いただけで何かが変わるアプリがあります。たとえば WordPress は「投稿を追加」を開いた時点で下書きを 1 件作ります。そういう画面が分かっていれば `--exclude` で外してください。止められないシステムでは、先に作った人に確かめてください。

詳しくは [しくみ（安全のための決まり）](docs/ja/how-it-works.md) と [安全の決まりの全文（英語）](references/safety-policy.md)。

## <img src="docs/readme/ui/icon-install.png" width="32" height="32" align="absmiddle" alt="" /> インストール

```bash
npx skills add akkijp/app-spec-crawler-skill
```

これで、スキルが Claude Code のスキルのフォルダに入ります。そのあと Claude Code に「app-spec-crawler の doctor を実行して」と頼むと、ほかに何が要るかが分かります。

または、Claude Code に次の文を貼ってください。Claude が git で入れ、コマンドを使えるようにして、動くかどうかまで確かめます。

```text
Claude Code のスキル app-spec-crawler をインストールしてください。

1. git clone https://github.com/akkijp/app-spec-crawler-skill.git ~/.claude/skills/app-spec-crawler
   （既にあれば上書きせず、私に聞く）
2. mkdir -p ~/.local/bin && ln -sf ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler
3. app-spec-crawler doctor を実行して、結果をそのまま見せて。
4. NG があれば理由と直し方を説明して。インストールなど直す操作は、私が承認してから行って。
```

必要なもの: macOS・Google Chrome・[browser-use](https://github.com/browser-use/browser-use)・Claude Code。詳しくは [docs/ja/install.md](docs/ja/install.md)。

コマンドの表示は英語です。Claude が日本語で説明します。

## <img src="docs/readme/ui/icon-use.png" width="32" height="32" align="absmiddle" alt="" /> 使い方

1. 対象のアプリに Chrome でログインしておく
2. Claude Code に頼む

```text
https://app.example.com/admin/ 以下を巡回して、仕様書を作って
```

巡回 → 画面ごとの説明 → 画面仕様書の作成 → システム概要書の作成 → 見た目の確認まで Claude が進め、できた文書の場所を返します。

## <img src="docs/readme/ui/icon-time.png" width="32" height="32" align="absmiddle" alt="" /> かかる時間と費用

手元の WordPress の管理画面（中身は架空）で測った値です。

- 50 画面の巡回に 8 分 46 秒
- 50 画面ほどで、頼んでから文書ができるまで約 20 分
- システム概要書は `claude -p` で書きます。費用の上限は既定で 8 ドルです（`--budget`）。画面ごとの説明は、使っている Claude Code の会話の中で書きます

アプリの大きさと、画面が描かれる速さで変わります。

## <img src="docs/readme/ui/icon-limits.png" width="32" height="32" align="absmiddle" alt="" /> できないこと

- 今のところ macOS だけです。
- クリックしないと出ない画面（モーダル、手順を進める画面、ボタンの先にあるもの）は撮れません。
- アプリが初回だけ出す案内の窓は、スクリーンショットに写ったままになります。閉じるにはクリックが要るためです。
- 後から描かれる画面は最長 8 秒待ちます（`--settle-max`）。それでも描きかけで撮れることがあります。
- ボタンを押すとどうなるかは、すべて「推定」です。押して確かめてはいません。
- 仕様書に書かれるのは、1 つのアカウントから見える範囲です。別の権限は、別に巡回が要ります。

## <img src="docs/readme/ui/icon-please.png" width="32" height="32" align="absmiddle" alt="" /> お願い

自分のシステムか、文書にしてよいと認められたシステムで使ってください。他社の製品の画面が入った仕様書は、その会社のものです。公開する前に確かめてください。

このプロジェクトに、トークン・コイン・有料版はありません。このリポジトリが唯一の正式な配布元です。

## <img src="docs/readme/ui/icon-more.png" width="32" height="32" align="absmiddle" alt="" /> もっと詳しく

- [インストールと必要なもの](docs/ja/install.md)
- [使い方の詳細](docs/ja/usage.md) — コマンド、オプション、エラーのとき
- [しくみ](docs/ja/how-it-works.md) — 処理の流れ、できあがる文書、安全のための決まり

## <img src="docs/readme/ui/icon-contact.png" width="32" height="32" align="absmiddle" alt="" /> 連絡先

不具合や、うまく撮れない画面を見つけたら、issue を立ててください。協業や取材など、issue に合わない用件は、作者のサイトからどうぞ。

<p>
  <a href="https://github.com/akkijp/app-spec-crawler-skill/issues/new"><img alt="Open an issue" src="https://img.shields.io/badge/GitHub-Open_an_issue-4F6BFF?style=for-the-badge&labelColor=0F1320&logo=github&logoColor=white" /></a>
  <a href="https://akki.jp"><img alt="akki.jp" src="https://img.shields.io/badge/Web-akki.jp-5B6B9A?style=for-the-badge&labelColor=0F1320" /></a>
</p>

## <img src="docs/readme/ui/icon-license.png" width="32" height="32" align="absmiddle" alt="" /> ライセンス

[MIT © akki](LICENSE)
