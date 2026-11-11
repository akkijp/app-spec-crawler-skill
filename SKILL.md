---
name: app-spec-crawler
description: Connects with browser-use to the user's running, logged-in Chrome (falls back to computer-use), crawls every page of a web application under a given URL in read-only mode, screenshots every page, modal, tab and menu, and produces an HTML screen spec (with index.html) in four layers - app-wide spec, section (URL directory) spec, screen spec, screen captures. Always use this skill for requests such as "write a spec for this app", "document every screen", "survey all the screens", "take screenshots of the whole app and put them together", "reverse-engineer this existing system", "list all screens and features", "here is a URL, find out what is in it" - even when the word "spec" is not used. Japanese triggers - 「このアプリの仕様書を作って」「画面を全部調査して」「スクショを撮ってまとめて」「既存システムのリバースエンジニアリング」「画面一覧・機能一覧を洗い出して」「URLを渡すので中身を調べて」. Chinese - 「给这个应用写一份规格说明书」「把所有页面都调查一遍」. Spanish - "haz la especificación de esta aplicación", "documenta todas las pantallas". Korean - 「이 앱의 명세서를 만들어 줘」「모든 화면을 조사해 줘」. Never performs an operation that changes data (save, update, delete, send). At the end it has claude -p (Fable 5.1) write guide.html, a one-page system guide for newcomers. The documents are written in the language of the user's conversation (en, ja, zh, es, ko). Pages are light-theme only. "/app-spec-crawler" or "app-spec-crawler help" shows usage; "app-spec-crawler doctor" shows whether the skill can run right now.
---

# app-spec-crawler — read-only crawl of a web app and screen spec generation

Survey every page and every "safe interaction state" (modals, tabs, menus, expanded panels) of the target app, with screenshots,
**without changing anything in the app**, and build an HTML screen spec in four layers.

| Layer | File | Content |
|---|---|---|
| App-wide spec | `overview.html` | Spec items for the whole app (SPEC-APP-NN), authentication and permissions, shared UI, navigation, business domain |
| Section spec | `sections/<path>.html` | Per URL directory: "this section holds these screens, and they share these specs". Deep sections nest and link to child sections and their screens |
| Screen spec | `pages/pXXX.html` | One file per screen. Lists "this screen has these specs" as numbered spec items (SPEC-pXXX-NN), each pointing to a capture as evidence |
| Screen captures | `captures/pXXX.html` | One file per screen. The initial view plus screenshots of each interaction state. Kept apart from the spec, linked both ways |

`index.html` is the hub for these (section tree, screens by category, capture list, safety report).
Last, a readable **`guide.html`, written by Fable 5.1 through `claude -p`** from the content of the four layers, is added (what you can do, map of the screens, workflows, rules, terms, things to confirm) and linked from the cover and the top bar.
Pages are **light-theme only** (they stay light when the OS is dark; no `prefers-color-scheme` is written).

**Where the command is.** The commands below are written as `app-spec-crawler …`. If that name is not on the PATH (for example when the skill was installed with `npx skills add`, which only copies this folder), run `bin/app-spec-crawler` inside this skill's own folder instead — the folder that contains this SKILL.md. Everything else is the same.

The parts of the output that should be deterministic (same input → same output) are done by programs.
The AI's (your) job is limited to reading what each screen means and writing the descriptions.

```
app-spec-crawler/
├── SKILL.md                    ← this procedure
├── bin/app-spec-crawler        ← command entry point (linked from ~/.local/bin: help / doctor / crawl / describe / build / write / verify)
├── scripts/
│   ├── app_spec_crawler.py     ← the command itself (standard library only; prints the cause of an error and how to fix it)
│   ├── bu_crawl.py             ← ① the crawl, run inside browser-use (open by URL, screenshot, extract structure, in-page tabs)
│   ├── bu_verify.py            ← ⑤ the visual check, run inside browser-use (widths 1440/390; stays light with the OS set to dark)
│   ├── build_book.py           ← ③ generates the four-layer HTML book (standard library only, deterministic)
│   ├── safety_rules.json       ← forbidden keywords etc. (adjustable)
│   ├── crawl.py                ← (optional, not used by default) Playwright-based crawl
│   └── requirements.txt        ← for crawl.py (Playwright). Not needed for the browser-use crawl
├── references/
│   ├── safety-policy.md        ← what is forbidden and how it is enforced (read it)
│   ├── description-guide.md    ← ② how to write descriptions.json, and the quality bar
│   ├── guide-prompt.md         ← ④ the prompt `write` gives to Fable (structure and style of the system guide)
│   └── manual-crawl.md         ← browser-use cautions, and the procedure for a manual crawl with computer-use
└── assets/book.css
```

## When called as a command (look here first)

Route by the argument of `/app-spec-crawler`, or by what the user said. In every case **show the result to the user as it is** (do not over-summarize).

| How it was called | What to do |
|---|---|
| No argument (`/app-spec-crawler`), or `help` | Run `app-spec-crawler help` and show the usage it prints. Do not start a crawl |
| `doctor` ("can I use it?", "is it set up?") | Run `app-spec-crawler doctor [--url TARGET_URL]` and show the table. If there is an NG or a warning, show the fix and **ask the person before fixing anything** |
| A URL, or "write a spec" | Go to "2. Procedure" below. Run `doctor` first and confirm there is no NG before crawling |

### When something is missing or a command fails
- If a command fails, show its "✖ error / cause / fix" output **as it is** and add one sentence on why it happened. Exit codes: 2 usage / 3 login expired / 4 cannot connect to Chrome / 5 a requirement is missing / 6 the visual check found problems / 7 generation failed / 8 writing with Fable failed.
- **Get the person's approval before any fix.** That includes installing packages (`uv tool install browser-use` etc.), `browser-use mac-approve` and `--reload`, editing the skill's files, and re-running with an added `--exclude`. For things only a person can do (allowing Chrome remote debugging, logging in again), show the steps and wait.
- If a package is missing, say what it is needed for and the command that installs it, and ask whether to install it. Once approved, install it and run `doctor` again to confirm OK.

### Is Playwright needed?
**No.** Both the crawl and the visual check use browser-use. Playwright is needed only when the user explicitly chooses `scripts/crawl.py` (an optional alternative).

## Language of the documents

Write the documents in **the main language of the user's conversation**.

| The user is talking in | Run | Write values in |
|---|---|---|
| English | `app-spec-crawler describe DIR --lang en` | English |
| Japanese | `app-spec-crawler describe DIR --lang ja` | Japanese |
| Simplified Chinese | `app-spec-crawler describe DIR --lang zh` | Simplified Chinese |
| Spanish | `app-spec-crawler describe DIR --lang es` | Spanish |
| Korean | `app-spec-crawler describe DIR --lang ko` | Korean |
| Any other language | `app-spec-crawler describe DIR --lang en` | English — and tell the user that the documents are in English because their language is not one of the five supported |

- `--lang` sets the language of the frame (headings, table columns, navigation, the system guide). Write **every value** in `descriptions.json` in that same language.
- `descriptions.json["_lang"]` records the choice. `build` and `write` follow it; you do not pass the language again (both accept `--lang <code>` to override it for one run).
- A project created before this rule existed has no `_lang`. It is treated as Japanese.
- The `confidence` field always uses exactly `Verified`, `Inferred` or `To confirm` — in English, in every language. The book translates the label.
- Quote UI labels of the target app exactly as they appear on screen. Never translate them.
- If the user asks for a specific document language ("write it in English"), that request wins over the conversation language.
- Talk to the user — progress, questions, the final report — in the user's language, whatever the document language is.

## 0. Absolute prohibitions (highest priority)

The target is often a customer's production system. **Never change, update, delete or send application data, or change settings, for any reason.**
Buttons and links such as "Edit", "Save", "Register", "Update", "Send", "Submit", "Confirm", "Delete", "Approve", "Publish", "Log out" (in a Japanese UI: 「編集」「保存」「登録」「更新」「送信」「確定」「削除」「承認」「公開」「ログアウト」) are **looked at, never pressed**.
Do not type into forms. Do not choose files. Always cancel confirmation dialogs.

The browser-use crawl (`app-spec-crawler crawl`) only **opens screens by URL** (GET only). The code contains nothing that types or submits.
The only thing it clicks is an in-page tab pointing at `#name` on the current page (`--no-tabs` turns that off). It does not open URLs containing logout / delete / approve / export and the like.
By default it also refuses URLs that carry a state-changing token or a non-read-only action parameter (see "What the crawl opens and what it refuses" below).
When crawling by hand with computer-use, the same standard applies: when in doubt, do not press. Details are in `references/safety-policy.md`.
(If the optional `crawl.py` is used, **never** use `--allow-mutations` on a customer system.)

**One limitation to be honest about:** an app can still change something merely because a page was opened. WordPress, for example, creates an auto-draft every time the "Add Post" screen loads. The crawler cannot know this. When such a screen is known, exclude it with `--exclude`; when you suspect one, ask the user before crawling.

## 1. Choosing the method

| Situation | Method |
|---|---|
| `doctor` says it can run (browser-use connects to the user's Chrome) **← first choice** | `app-spec-crawler crawl` (browser-use. Consistent decisions, a coverage log is kept, Chrome is not brought to the front) |
| browser-use cannot be used or installed, or the user said "use computer-use" | Crawl by hand with computer-use (the Computer Use procedure in `references/manual-crawl.md`) |
| The user explicitly chose the Playwright method | `scripts/crawl.py` (optional. Needs `pip install -r scripts/requirements.txt && playwright install chromium`; get approval before installing) |

**The output format (`pages.json` + `screenshots/`) is the same** for every method, so the book generation in ③ works unchanged.

### What to ask the user (once, at the start, all together)
1. The start URL and the scope (the whole origin, or only under `/admin/`, etc.)
2. Whether they are logged in to the target app in their usual Chrome (browser-use connects to the whole running Chrome; a profile cannot be chosen).
   If Chrome remote debugging is off, have them allow it at `chrome://inspect/#remote-debugging` (`doctor` tells you).
3. The page limit (default 300), and whether the app switches screens with a query such as `?page=` (if so, `--route-param`)
4. Whether any screen changes something just by being opened (to exclude with `--exclude`), if they know of one
5. The output location (employee names and the like appear in the screenshots, so recommend a place that is not in git)

If the instructions already cover these, start without asking.

## 2. Procedure

### ① Crawl (browser-use)
```bash
app-spec-crawler doctor --url https://app.example.com/          # confirm there is no NG
app-spec-crawler crawl --url https://app.example.com/ --out ./spec_out

# An app that switches screens with a query (?page=...)
app-spec-crawler crawl --url "https://app.example.com/admin/<token>?page=/top" --out ./spec_out \
    --route-param page --variant-param tab --allow-route /export/select
```
- It connects to the user's Chrome over a dedicated connection (`BU_NAME=app-spec-crawler`), creates one working tab and crawls in it. The user's tabs are not touched. The first time, Chrome shows a permission prompt (the person presses it, or, with approval, run `BU_NAME=app-spec-crawler browser-use mac-approve`).
- It crawls in batches of 30 screens and writes `state.json` after every screen. If it stops, `--resume` continues from where it left off. When the login expires it stops with exit code 3; have the person log in again and `--resume` with the new URL.
- **A screen is captured after it has finished rendering.** The crawler waits until the page stops changing: at least `--wait` seconds (default 1), at most `--settle-max` seconds (default 8). Raise `--settle-max` for an app that loads its content slowly.
- **Screens whose content is identical to one already captured are recorded as duplicates and not added** to the book. `--no-dedupe` turns this off (use it when distinct URLs legitimately show the same content and each must appear).
- When an external guidance tool (in-site help, a chat widget) overlaps the screen, hide it just before the capture with `--hide <CSS selector>` (repeatable). Find the selector with the developer tools on the target app.
- Destinations of `onclick="location.href=..."` on buttons are picked up too. In-page tabs pointing at `#name` on the current page are clicked and captured as `states`.

#### What the crawl opens and what it refuses
Some apps change data on a plain GET link (WordPress "Trash" and "Activate" are links, not forms). So, by default, the crawler refuses to open:
- any URL whose path or query contains a dangerous keyword (`logout`, `delete`, `approve`, `export` … — `deny_url_keywords` in `scripts/safety_rules.json`);
- any URL that carries a **state-changing token** — a query parameter such as `_wpnonce`, `csrf_token`, `authenticity_token`, `sesskey`;
- any URL with an **action parameter** (`action=`, `do=`, `op=`, `cmd=`, `task=`) whose value is not a known read-only one (`edit`, `view`, `show`, `list`, `search` …).

Every skipped URL is listed in `safety_report.json` with the reason.
- `--allow-route PATH` re-admits one specific screen (repeatable). Use it after checking that the screen only displays something, and after confirming with the user.
- `--allow-token-urls` disables the token rule entirely. **Dangerous.** Use it only on a test system and only when the user explicitly asks for it. Never on a customer's production system.

Output: `spec_out/pages.json` (structure, links, forms, buttons and interaction states of every page), `spec_out/screenshots/pXXX.png` (initial view) and `pXXX_cNN.png` (tabs), `spec_out/safety_report.json`, `spec_out/crawl.log`, `spec_out/state.json` (the ledger used to resume).

Check after the crawl:
- Look at `skipped_urls` in `safety_report.json` (screens not opened because of a dangerous keyword, a token or an action parameter). If a plain list screen was left out, confirm with the user, then add it with `--allow-route`.
- Look at the screens recorded as duplicates (`duplicates` in `safety_report.json`; they also appear in `skipped_urls` with the reason `Duplicate of pXXX`). If two different screens were merged, re-run with `--no-dedupe`.
- If there are `errors`, either `--exclude` those URLs or run again with `--resume`.
- If the number of screens reached `--max-pages`, raise the limit and `--resume`.

### ② Write the screen descriptions (AI)
```bash
app-spec-crawler describe ./spec_out --lang <code>   # generates the descriptions.json template (see "Language of the documents")
```
Fill in `spec_out/descriptions.json`. This is the core of the skill, and it is your job. The template lists the
**sections (`sections`)** and **screens (`pages`)** generated from the URLs. Write in the order **screens → sections → whole app**,
not whole app → sections → screens (looking at individual screens first, then lifting what they share to the section and the app, is more accurate).
For each page, read its record in `pages.json` and **look at the screenshot with your own eyes** (open the image with Read) before writing.
How to write, the quality bar and good examples are in `references/description-guide.md`.

Write every value in the language recorded in `descriptions.json["_lang"]`. `confidence` is exactly `Verified`, `Inferred` or `To confirm`.

**The spec items (`specs`) are the substance.** Write specs at three levels — `app.specs` / `sections[path].common_specs` / `pages[pXXX].specs` —
in the form `{type, statement, condition, evidence, confidence}`. Put `init` or a state id such as `c02` in `evidence`, and
the book links the item to that image in the captures. Lift a spec that is not specific to one screen up to the section or the app; do not repeat the same sentence on each screen.

Supporting fields per screen:
- `name` (screen name) / `category` (feature category) / `summary` (1–2 sentences)
- `purpose`: the business purpose
- `display_conditions`: when, to whom and in which state it is shown or not shown (permissions, presence of data, prior steps)
- `users_and_usage`: intended users and how they use it
- `features`: main features, as a list
- `ui_elements`: behavior of each button, link and input (mark anything not pressed as inferred)
- `inputs`: input fields, whether required, assumed validation
- `flows`: expected usage flow (steps)
- `transitions`: navigation to other screens
- `states_and_variants`: variations such as empty state, errors, permission differences
- `business_rules`: inferred business rules
- `open_questions`: unknowns (put them here; do not fill them with guesses)
- `states.cNN`: description and display condition of each interaction state (modal etc.)

With many pages you may split the work across subagents by category, but each agent must look at the screenshots too.
Distinguish fact (what was seen) from inference (what is probably so) in the text.

### ③ Build the book (program)
```bash
app-spec-crawler build ./spec_out        # → ./spec_out/book/index.html
```
This generates `book/index.html`, `overview.html`, `sections/*.html`, `pages/*.html` and `captures/*.html`.
Unfilled places show a "to fill in" placeholder, and the run prints how many screens and sections are filled; repeat ② and ③ until nothing is unfilled.
If a section with two or more screens has an empty `common_specs`, the run says so; lift the specs that recur within the section (shared tabs, the shape of display conditions, button color coding, etc.).

How the book looks (`assets/book.css` and the templates in `build_book.py`):
- **The top bar has two rows.** Row 1 has the app name and a **switch** between the two documents ("System guide — read first (one page)" / "Screen spec — per-screen specs and screenshots"; the current one is filled). Pressing it changes the page layout (a one-column read ⇔ a book with a table of contents on the left), so it is not placed in the same row as the ordinary menu. Row 2 appears only in the book: the menu inside the screen spec (Top / App-wide spec / Section specs / Screens / Safety; the current place is underlined). On a phone the app name is hidden and the switch takes the full width.
- Every page has a permanent per-section table of contents of screens on the left; the current screen is highlighted and scrolled to the middle.
- A screen spec opens with one card (screen name, `summary` as a slightly larger sentence, count badges [specs n · verified / inferred / to confirm · captures n], path, section, route to reach it, URL). A long URL with a token is shortened to one line; pressing it shows the full text.
- The body is one white card per part. With three or more parts an in-page table of contents (one horizontal row, scrollable) is added. Purpose / display conditions / users, and variants / business rules (for a section: role / screens / navigation / access) are short, so they sit side by side in one card.
- Spec tables do not wrap the ID, type, evidence and confidence columns. At phone width the ID column is hidden.
- The top page has number tiles, section cards, and screen cards with thumbnails by category. The capture list is collapsed.
- **Light-theme only.** It stays light when the OS is dark (`color-scheme: light` and `<meta name="color-scheme" content="light">`; no dark media query is written).

### ④ Have Fable write the system guide (always, at the end)
```bash
app-spec-crawler write ./spec_out        # → ./spec_out/book/guide.html (a few minutes; cap --budget, default 8 dollars)
```
- Internally it calls `claude -p --model claude-fable-5-1 --tools "" --permission-mode dontAsk --effort high`. Standard input is the prompt in `references/guide-prompt.md` (the CLI fills in the language and the three confidence labels) plus the material (the fields of `descriptions.json` the guide needs, and the list of files it may link to, under `available_files`).
- The guide is written in the language of `descriptions.json["_lang"]`.
- Fable writes only `<article class="guide">`. The command strips script/style/on… attributes and links or images pointing at files that do not exist, saves the body to `DIR/guide_body.html`, and `build` puts it into the frame with the top bar (the switch) to make `book/guide.html`. After changing the frame or the bar, `build` alone applies the change; Fable does not need to write again.
- When it is written, **Claude reads guide.html and checks it against the material.** If a number, screen name or button label differs from the material, a fact not in the material was added, an "inferred" became a certainty, or a personal name appears — fix guide.html directly (and report what you fixed).
- The reader is a newcomer (a client, a new team member, a non-engineer in charge). To change the structure, edit `guide-prompt.md`.
- If `claude` is missing, the login has expired or the cap was reached, exit code 8 (or 5) and the cause are printed. Raising the cap, installing and logging in again all need the person's approval first.

### ⑤ Verify and deliver
- Run `app-spec-crawler verify ./spec_out`. It opens the top page, the system guide, the app-wide spec, a section, a screen spec and a capture page with browser-use at widths 1440px and 390px, **with the OS set to dark**, captures them into `spec_out/verify/`, and counts overflow, unreadable images, dark backgrounds (whether light-only still holds) and leftover "to fill in" placeholders (exit code 6 if there is a problem). **Open the captured images with Read and look at them yourself.**
  - Checked by machine: `document.documentElement.scrollWidth` of each page does not exceed the viewport width (no horizontal overflow); images that failed to load (`img.complete && naturalWidth===0`) are 0; no "to fill in" placeholder remains under `book` (`要記入` in a Japanese book, `(to fill in)` in an English one).
  - Checked by eye: marks and IDs in tables do not wrap mid-way; the current screen is highlighted in the left table of contents; no overlay that is not part of the app (a guidance tool etc.) appears in a screenshot; no screenshot shows a half-rendered screen (spinner, skeleton, empty frame) — if one does, re-crawl that screen with a larger `--settle-max`. If the section tree does not match the real menu structure, rename sections with `sections[path].name` (the tree itself is built deterministically from URLs).
- Confirm that the number of pages matches the count in `pages.json` and that `safety_report.json` has no unblocked state-changing request.
- Zip the `book/` directory and hand it over (the screenshots are included, so it opens on its own).
- On delivery, add in one line: the crawl scope, the number of pages, the number of elements not pressed, the number of URLs not opened (with the main reasons), and the number of blocked requests.
- Give the final report in the user's language.

## 3. Common problems

- **`doctor` reports NG for "Chrome remote debugging"**: have the user allow it at `chrome://inspect/#remote-debugging` (a person's action).
- **browser-use does not return (exit code 4)**: Chrome's permission prompt is still showing. Have the person press it, or, with approval, `BU_NAME=app-spec-crawler browser-use mac-approve`.
- **Redirected to the login screen, or "session is invalid" (exit code 3)**: have the person log in again, then `crawl --resume` with the new URL. For an app whose expiry message is not detected, add it with `--session-text`.
- **An SPA whose links are not `<a href>`**: the browser-use crawl does not press buttons, so JS navigation other than `onclick="location.href"` is not picked up. For missing screens, open them by hand with computer-use and append them to `pages.json`, or ask the user for the URLs and use them as starting points with `--resume`.
- **Screens captured half-rendered** (spinner, skeleton, empty tables): the page was still changing at `--settle-max`. Raise `--settle-max` (and `--wait` if the page shows nothing at first) and re-crawl those screens.
- **Pages multiply without end (calendars, pagination)**: narrow with `--exclude '[?&]page=' --exclude '/calendar/\d{4}'` and the like. URLs with IDs (/users/123) are collapsed to `{id}` by default. Screens with identical content are dropped as duplicates unless `--no-dedupe` is given.
- **Many screens skipped for a token or action parameter**: this is the default protection. Count `skipped_urls` in `safety_report.json` by reason, look at the large groups, and re-admit only screens that just display something, one by one with `--allow-route`, after confirming with the user. Do not reach for `--allow-token-urls` on a production system.
- **A screen that changes data just by opening** (e.g. WordPress "Add Post" creates an auto-draft on load): the crawler cannot detect this. Exclude it with `--exclude` before the crawl. If one was opened by mistake, stop, tell the user what was opened and when, and do not try to undo it yourself.
- (Only when using `crawl.py`) For profile locks, GraphQL POSTs, `--click-mode` and so on, see `python scripts/crawl.py -h`.
- **A guidance tool's popup covers every screen**: it is not the app itself, so set it to `display:none` just before the capture with `--hide <CSS selector>` (do not click it closed; "Stop the guide" and the like change the user's settings). In the spec, write just one line in the app-wide spec: "an external tool overlaps the screen".
- **An app that moves between screens with buttons** (`<button onclick="location.href='...'">`): collecting links alone misses whole areas such as settings. The `location.href` in onclick is collected as a destination too (it is a GET, so it may be opened; the dangerous-URL check applies the same way).
- **In-page tabs** (`<a href="#xxx_contents">`): changing only the end of the URL (#) sometimes does not switch the tab. In-page link tabs may be clicked (nothing is sent to the server), so they are captured as `states`.
- **Capture deep and long screens in full (depth and length are no reason to miss anything)**: this is a spec, so deeply nested screens, very tall screens and screens with an inner scroll frame must not be missed. `bu_crawl.py` receives the structure via `JSON.stringify` and reads form and input names with `getAttribute()` (in a form with an input named `name="name"` or `name="id"`, `form.name` returns the input element itself, and the crawl used to fail with `Object reference chain is too long`); it expands inner scroll frames before capturing, and adds anything beyond 6000px to `states` (`s02` …) as continuation images `pXXX_s02.png` …. Body text is taken up to 40000 characters. If `errors` remain in `pages.json` after the crawl, fix the cause and capture again with `--resume` (do not settle for "could not capture"). This has really happened: screens with many inputs, screens cut at 6000px, and screens where only the top of an inner scroll frame was captured.
  - To repair output crawled before this fix: reopen every screen, re-capture only those whose expanded height is taller than the previous image, and replace `states` and `bodyText` (rewrite the description for those screens only). Before re-capturing, check that the URL and title of the opened screen match the record (some entry points redirect to "the screen used last", and you could overwrite with a different screen). Expanding an inner scroll frame occasionally makes text overlap in the image. If so, say it in one line in the screen description.
- **Some apps lose most of their screens if `/edit`, `/new` and `import` are excluded across the board**: in apps such as attendance-management SaaS, where list and settings screens themselves have URLs like `/client/edit-employee`, merely opening them changes nothing. After the crawl, count `skipped_urls` in `safety_report.json` by reason, look inside the large groups, and, after confirming with the user, put them back into `queue` in `state.json` and `--resume`. Do not put back anything that may run a process just by being opened, such as `sync` or `download`.
- **An entry point that enters a different service by query** (e.g. `…/login?d=tm` enters talent management): by default the query is dropped and URLs are merged, so another service on the same domain is missed entirely. Crawl each entry point into its own `--out`, or use `--keep-query`.
- **A separate app per subdomain** (SaaS where the shared ID, attendance, HR and payroll live on separate subdomains): `crawl` covers a single origin (`--scope-prefix`). First open the OAuth URL that enters each app from the shared ID to establish the login, crawl each app into its own `--out`, and tie them together with an entry `index.html`.
- **Sent back to a login screen on the same domain** (e.g. `/login/client/?url=…`, `/users/sign_in`): a login can expire in about an hour, and then you are redirected to a login screen on the same domain. Because that stays in scope, a check of "out of scope = login expired" alone would keep capturing the login screen as content. `bu_crawl.py` stops with exit code 3 as "login expired" when the URL path has the shape of a login screen (`/login`, `/sign_in` etc.) and the screen has a password field.
  - When it stops, log in again (the person, or an approved procedure), then `--resume`. When crawling several apps under one shared ID, an expired shared-ID login locks out all the apps at once, so check that the login is still alive after each app.
  - **Behavior when the login expires**: by default it stops (exit code 3; the person logs in again and runs `--resume`). Add `--relogin "<command>"` only when the user has decided that logging in again automatically is acceptable. Each time an expired login is detected, that command is run (it receives the environment variables `BU_NAME` `BU_CDP_WS` `ASC_OUT` `ASC_URL`), and on exit code 0 the crawl continues. It stops if `--relogin-max` (default 3 times) is exceeded, the command fails, or `--relogin-timeout` (default 180 seconds) passes.
    - The user provides the login command (the skill holds no password). It creates a working tab with `new_tab()`, logs in there, and closes it when done. It does not touch the user's tabs.
    - Read secrets from 1Password **only once**: wrap the whole crawl, as in `op run --account <account> --env-file <.env with references only> -- app-spec-crawler crawl ... --relogin "python3 login.py"`, and have login.py read from environment variables. Calling `op` on every re-login raises an approval prompt each time, and the crawl stops when an approval times out.
    - If the login expires again right away on the same screen however many times you log in, that screen may be one that "logs you out when opened". When it stops, look at the last URL in crawl.log and consider `--exclude`.
  - When you write a script that reopens screens outside the crawl (re-captures etc.), put in the same check and **never overwrite an existing image with a login screen** (before overwriting, confirm the screen is not a login screen). If you did overwrite one, it can be restored from the copy in `book/screenshots/`.
  - When you run a browser-use script outside the crawl, first create a working tab with `new_tab()`, or note the working tab's ID and `switch_tab()` to it, before acting. If you run a script that only calls `goto_url()` after the working tab was closed with `close_tab()`, it will drive another tab the connection is attached to (a tab of the user's).
- **An app with a session token in the URL** (`/admin/{token}?page=...`): it expires after a period without activity, so crawl without long gaps. If `norm_url` is built by treating the route-param value as a path, the section tree matches the menu structure.
