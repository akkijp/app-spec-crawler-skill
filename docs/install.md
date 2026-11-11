# Installation and requirements

[← Back to the README](../README.md) · [日本語](ja/install.md)

## Requirements

| What | Used for | How to get it |
|---|---|---|
| macOS | The check of how Chrome is connected is written for macOS | — |
| Google Chrome | The browser in which you are logged in to the target app | — |
| Chrome remote debugging allowed | So that browser-use can connect to Chrome | Open `chrome://inspect/#remote-debugging` in Chrome and turn on "Allow remote debugging for this browser instance". Chrome asks for confirmation the first time something connects |
| [browser-use](https://github.com/browser-use/browser-use) | The crawl and the visual check | `uv tool install browser-use` (if you have no uv: `brew install uv`) |
| Python 3.9 or later | The command itself (standard library only) | The one that ships with macOS is fine |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (the `claude` command, logged in) | Writing the screen descriptions and the system guide (`claude -p`) | The official instructions |
| zip (optional) | Handing over the finished documents | Ships with macOS |

- Playwright is not needed. It is needed only if you explicitly use the Playwright-based crawl (`scripts/crawl.py`).
- Where browser-use cannot be used, there is also a procedure in which Claude looks at the screen with computer-use and crawls by hand ([`references/manual-crawl.md`](../references/manual-crawl.md)).

`app-spec-crawler doctor` checks these one by one. For anything missing it prints what it is needed for and how to fix it.

## Manual install

```bash
git clone https://github.com/akkijp/app-spec-crawler-skill.git ~/.claude/skills/app-spec-crawler
mkdir -p ~/.local/bin
ln -sf ~/.claude/skills/app-spec-crawler/bin/app-spec-crawler ~/.local/bin/app-spec-crawler
app-spec-crawler doctor
```

- Name the folder `app-spec-crawler` (it must match the skill's name).
- If `~/.local/bin` is not on your PATH, add `export PATH="$HOME/.local/bin:$PATH"` to your shell configuration.

## Language

Nothing to install or configure. The skill writes the documents in the language you talk to Claude in: English, Japanese, Simplified Chinese, Spanish or Korean. In any other language the documents are in English. See [usage](usage.md#language-of-the-documents).

## Updating

```bash
cd ~/.claude/skills/app-spec-crawler && git pull
```
