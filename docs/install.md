# インストールと必要なもの

[← README に戻る](../README.md)

## 必要なもの

| もの | 用途 | 入れ方 |
|---|---|---|
| macOS | Chrome とのつなぎ方の確認が macOS 向け | — |
| Google Chrome | 対象アプリにログインしておくブラウザ | — |
| Chrome の遠隔デバッグの許可 | browser-use が Chrome につなぐため | Chrome で `chrome://inspect/#remote-debugging` を開き「Allow remote debugging for this browser instance」を有効にする。初めてつなぐとき Chrome に確認が出る |
| [browser-use](https://github.com/browser-use/browser-use) | 巡回と見た目の確認 | `uv tool install browser-use`（uv が無ければ `brew install uv`） |
| Python 3.9 以上 | コマンド本体（標準ライブラリのみ） | macOS 標準のもので可 |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（`claude` コマンド、ログイン済み） | 画面の説明を書く・システム概要書を書く（`claude -p`） | 公式の手順 |
| zip（任意） | できた文書を渡すとき | macOS 標準 |

- Playwright は不要です。Playwright 方式の巡回（`scripts/crawl.py`）を明示して使うときだけ要ります。
- browser-use が使えない環境では、Claude の computer-use で画面を見ながら手で回す手順もあります（[`references/manual-crawl.md`](../references/manual-crawl.md)）。

`app-spec-crawler doctor` がこれらを 1 つずつ確かめ、足りないものは「何に要るか」と「直し方」を出します。

## 手で入れる

```bash
git clone https://github.com/akkijp/app-spec-crawler-skill.git ~/.claude/skills/app-spec-crawler
mkdir -p ~/.local/bin
ln -sf ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler
app-spec-crawler doctor
```

- フォルダ名は `app-spec-crawler` にしてください（スキルの名前と合わせるため）。
- `~/.local/bin` が PATH に無ければ、シェルの設定に `export PATH="$HOME/.local/bin:$PATH"` を足します。

## 更新

```bash
cd ~/.claude/skills/app-spec-crawler && git pull
```
