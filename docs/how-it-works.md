# How it works

[← Back to the README](../README.md) · [日本語](ja/how-it-works.md)

## Flow

```
 ① crawl     Connects with browser-use to the user's Chrome (logged in),
             visits every screen just by opening URLs, and records a full screenshot and the structure of each
 ② describe  Claude looks at the screenshots one by one and writes the spec of each screen (descriptions.json)
 ③ build     Assembles the screen spec (HTML)
 ④ write     Through claude -p, Claude (Fable 5.1) writes the system guide from the screen spec
 ⑤ verify    Opens the finished documents with browser-use and checks for overflow, broken images and unfilled places
```

The crawl and the assembly are fixed processing (programs) and give the same result every time. The AI handles only ② and ④: reading what each screen means and writing it down.

During the crawl, a screen is captured after it has finished rendering (the crawler waits until the page stops changing, between `--wait` and `--settle-max` seconds), and a screen whose content is identical to one already captured is recorded as a duplicate and not added (`--no-dedupe` turns this off).

## The documents

| Document | Reader | Content |
|---|---|---|
| System guide (`guide.html`) | Newcomers, clients, people in charge who are not engineers | A one-page read. What you can do / who uses it and how / map of the screens / main workflows / feature by feature (with screen images) / rules / terms / things to confirm |
| Screen spec (`index.html` and others) | People doing development, maintenance or migration | Four layers: app-wide spec → spec per section (URL directory) → spec per screen → screen captures |

- Each spec item has a number (such as `SPEC-p012-03`) and a confidence (Verified / Inferred / To confirm), and links to the screenshot that supports it.
- The top bar switches between the two documents. The screen spec has a permanent table of contents on the left and is readable at phone width.
- Pages are light-theme only (they stay light when the OS is in dark mode).

## Language

- The documents are written in the main language of the user's conversation with Claude: `en` English, `ja` Japanese, `zh` Simplified Chinese, `es` Spanish, `ko` Korean. In any other language they are written in English.
- `describe --lang CODE` stores the choice in `descriptions.json` as `_lang`. `build` uses it for the frame (headings, table columns, navigation); `write` tells the model to write the guide in that language.
- A project with no `_lang` (created before this rule) is treated as Japanese.
- The `confidence` values in `descriptions.json` are always `Verified`, `Inferred`, `To confirm`. The book translates the label.
- UI labels of the target app are quoted as they appear on screen and are never translated.

## Safety rules

- Screens are only opened by URL. No typing, sending, saving or deleting. The only click is on a tab within the same page (a link to `#xxx`).
- URLs containing `logout` `delete` `approve` `export` and the like are not opened. Buttons whose text contains "Save", "Delete", "Approve" (「保存」「削除」「承認」) and the like are not pressed (adjustable in [`scripts/safety_rules.json`](../scripts/safety_rules.json)).
- URLs that carry a state-changing token (`_wpnonce`, `csrf_token`, `authenticity_token`, `sesskey` …) or an action parameter (`action=`, `do=`, `op=`, `cmd=`, `task=`) whose value is not a known read-only one (`edit`, `view`, `show`, `list`, `search` …) are not opened, because some apps change data on a plain GET link (WordPress "Trash", "Activate"). Skipped URLs are listed in `safety_report.json` with the reason. `--allow-route PATH` re-admits one screen; `--allow-token-urls` turns the rule off (dangerous; test systems only, on explicit request).
- When an expired login is detected the crawl stops, and continues after a person has logged in again.
- The tabs the user has open are not touched; the crawl creates one working tab of its own.

One limitation: an app can change something merely because a page was opened (WordPress creates an auto-draft when "Add Post" loads). The crawler cannot know this. Such screens must be excluded with `--exclude` when they are known.

Details are in [`references/safety-policy.md`](../references/safety-policy.md).

## Folder layout

```
app-spec-crawler/
├── SKILL.md                 The procedure Claude reads
├── bin/app-spec-crawler     Command entry point
├── scripts/
│   ├── app_spec_crawler.py  The command itself (help / doctor / crawl / describe / build / write / verify)
│   ├── bu_crawl.py          The crawl, run inside browser-use
│   ├── bu_verify.py         The visual check, run inside browser-use
│   ├── build_book.py        Assembles the screen spec
│   ├── safety_rules.json    The words not to press and not to open
│   └── crawl.py             (optional) Playwright-based crawl
├── references/
│   ├── safety-policy.md     The safety rules in detail
│   ├── description-guide.md How to write the per-screen descriptions
│   ├── guide-prompt.md      The prompt for writing the system guide
│   └── manual-crawl.md      browser-use cautions; crawling by hand with computer-use
├── docs/                    This page and the other details behind the README (Japanese under docs/ja/)
└── assets/                  The look of the documents (book.css) and the README images
```
