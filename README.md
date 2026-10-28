# app-spec-crawler

ログイン済みの Chrome に browser-use でつなぎ、Web アプリを **読み取り専用** で全ページ巡回して、
4層の HTML 画面仕様書（アプリ共通の仕様 / 階層仕様 / 画面仕様 / 画面キャプチャ、index.html 付き）を作る Claude スキル。

- 使い方・手順: `SKILL.md`（または `app-spec-crawler help`）
- 使えるかの確認: `app-spec-crawler doctor`
- 禁止事項と防護の仕組み: `references/safety-policy.md`
- 説明の書き方: `references/description-guide.md`
- browser-use の注意と、computer-use で手で回す手順: `references/manual-crawl.md`

## クイックスタート
```bash
app-spec-crawler doctor --url https://app.example.com/        # 準備の確認（NG なら直し方が出る）
app-spec-crawler crawl --url https://app.example.com/ --out ./spec_out
app-spec-crawler describe ./spec_out                          # descriptions.json を AI が記入
app-spec-crawler build ./spec_out                             # → spec_out/book/index.html
app-spec-crawler write ./spec_out                             # claude -p（Fable 5.1）がシステム概要書 book/guide.html を書く
app-spec-crawler verify ./spec_out                            # 見た目の確認（browser-use）
```

## 要るもの
- browser-use（`uv tool install browser-use`）と Google Chrome（遠隔デバッグを `chrome://inspect/#remote-debugging` で許可）
- Python 3.9 以上（標準ライブラリのみ）
- Claude Code の `claude` コマンド（ログイン済み。`write` で Fable 5.1 にシステム概要書を書かせる）
- 画面はライト固定（OS がダークでも明るいまま）
- Playwright は不要（任意の `scripts/crawl.py` を使うときだけ）

## インストール
Claude Code: `~/.claude/skills/app-spec-crawler/` にこのフォルダを置き、
`ln -s ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler` でコマンドを通す。
