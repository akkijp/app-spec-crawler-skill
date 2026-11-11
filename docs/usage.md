# Usage in detail

[← Back to the README](../README.md) · [日本語](ja/usage.md)

## Commands

| Command | What it does |
|---|---|
| `app-spec-crawler` / `help` | Prints the usage |
| `app-spec-crawler doctor [--url URL]` | Prints a table showing whether it can run now. With `--url` it also checks that a tab of that app is open |
| `app-spec-crawler crawl --url URL --out DIR` | Crawls (`DIR/pages.json` and `DIR/screenshots/`) |
| `app-spec-crawler describe DIR [--lang CODE]` | Creates `DIR/descriptions.json`, the template for the per-screen descriptions. `--lang` sets the language of the documents: `en`, `ja`, `zh`, `es` or `ko` |
| `app-spec-crawler build DIR` | Builds the screen spec `DIR/book/` |
| `app-spec-crawler write DIR` | Writes the system guide `DIR/book/guide.html` (a few minutes. `--budget` caps the cost; default 8 dollars) |
| `app-spec-crawler verify DIR` | Opens the documents, captures them at widths 1440px / 390px, and checks for overflow, broken images and unfilled places (`DIR/verify/`) |

Normally you just ask Claude "crawl … and write a spec", and Claude goes through these in order.

## Language of the documents

- Claude writes the documents (the screen spec and the system guide) in the main language of your conversation.
- Five languages are supported: `en` English, `ja` Japanese, `zh` Simplified Chinese, `es` Spanish, `ko` Korean. In any other language the documents are in English, and Claude tells you so.
- The choice is made with `describe --lang CODE` and stored in `descriptions.json` as `_lang`. `build` and `write` follow it (both accept `--lang CODE` to override it for one run).
- A project created before this rule existed has no `_lang` and is treated as Japanese.
- The `confidence` value in `descriptions.json` is always `Verified`, `Inferred` or `To confirm`, in English. The book shows the label in the document language.
- Labels of the target app's UI are quoted as they appear on screen. They are not translated.

## Options of crawl

| Option | Meaning |
|---|---|
| `--resume` | Continue a crawl that stopped. It continues even if the URL changed after logging in again |
| `--scope-prefix URL` | Crawl only URLs that start with this text (default: the same origin as the start URL) |
| `--route-param NAME` | For an app that switches screens with `?NAME=...`: treat that value as the address of the screen |
| `--variant-param NAME` | A query parameter that makes a separate screen (repeatable) |
| `--keep-query` | Treat URLs with different query strings as separate screens |
| `--no-id-collapse` | Do not treat `/items/1` and `/items/2` as the same screen |
| `--exclude REGEX` | URLs not to open (repeatable) |
| `--extra-deny WORD` | An extra word that marks a URL as dangerous (repeatable) |
| `--allow-route PATH` | A screen that may be opened although its URL has a dangerous word, a token or an action parameter (repeatable) |
| `--allow-token-urls` | Turn off the token and action-parameter rule entirely. **Dangerous.** Test systems only, and only when you explicitly ask for it |
| `--hide SELECTOR` | An overlay to hide before capturing (CSS selector of in-site help, a chat widget, etc.; repeatable) |
| `--max-pages N` | Maximum number of screens (default 300) |
| `--max-depth N` / `--batch N` | Maximum link depth (default 10) / screens per run (default 30) |
| `--wait SECONDS` | Minimum wait after a page opens (default 1) |
| `--settle-max SECONDS` | Longest wait for a page to finish rendering (default 8) |
| `--no-dedupe` | Do not merge screens whose content is identical |
| `--no-tabs` | Do not click in-page tabs either |
| `--session-text REGEX` | Extra text that means the login has expired (repeatable) |
| `--retry-errors` | Retry the screens that failed last time (use with `--resume`) |
| `--relogin COMMAND` / `--relogin-max N` / `--relogin-timeout SECONDS` | A command to run when the login expires (exit code 0 = logged in again) / how many times at most (default 3) / how long to wait for it (default 180) |

### When a screen is captured

A screen is captured after it has finished rendering. The crawler waits until the page stops changing: at least `--wait` seconds, at most `--settle-max` seconds. If screenshots show spinners or empty frames, raise `--settle-max`.

### Duplicate screens

A screen whose content is identical to one already captured is recorded as a duplicate and not added to the book. `--no-dedupe` turns this off.

### URLs the crawler refuses to open

Some apps change data on a plain GET link (in WordPress, "Trash" and "Activate" are links). By default the crawler does not open:

- a URL containing a dangerous word (`logout`, `delete`, `approve`, `export` …);
- a URL carrying a state-changing token — a query parameter such as `_wpnonce`, `csrf_token`, `authenticity_token`, `sesskey`;
- a URL with an action parameter (`action=`, `do=`, `op=`, `cmd=`, `task=`) whose value is not a known read-only one (`edit`, `view`, `show`, `list`, `search` …).

Skipped URLs are listed in `DIR/safety_report.json` with the reason. Re-admit a specific screen with `--allow-route PATH`.

## When there is an error

A failure is printed in three parts: "✖ error / cause / fix". When the fix includes installing a package or the like, Claude asks for your approval before doing it.

| Exit code | Meaning |
|---|---|
| 0 | Success |
| 1 | Other |
| 2 | Wrong usage |
| 3 | Login expired (log in again, then `--resume`) |
| 4 | Cannot connect to Chrome |
| 5 | A requirement is not installed |
| 6 | The visual check found a problem |
| 7 | Building the screen spec failed |
| 8 | Writing the system guide failed |

## Cautions

- **The spec covers only what is visible.** It includes inferences read from screenshots and screen structure. Check items marked "Inferred" or "To confirm" against the original design documents or with the developers.
- **Screenshots show real data.** Customer names, employee names and the like appear in them, so take care where you share and store the documents.
- **Opening a page can itself change something in some apps.** WordPress, for example, creates an auto-draft every time "Add Post" loads. The crawler cannot detect this. If you know such a screen, tell Claude so it is excluded with `--exclude`.
- **`write` costs Claude usage** (it calls `claude -p` once; `--budget` sets the cap).
- In an app with a short login lifetime the login may expire midway. Log in again and continue with `--resume`.
