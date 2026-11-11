# browser-use cautions and the manual crawl procedure — Browser Use / Computer Use / Claude in Chrome

Normally the crawl is done with `app-spec-crawler crawl` (browser-use; `scripts/bu_crawl.py`). "Cautions for the browser-use CLI" below explains how that works.
When browser-use cannot be used, or the user says "use computer-use", Claude looks at the screen and crawls by hand ("Procedure" below).
Because the AI makes the decisions, they vary more than a program's. So **keep strict records**, and produce the same output format as `bu_crawl.py` (the `pages.json` schema) to hand to `build_book.py`.
For safety, follow "Additional rules for a manual crawl" in `safety-policy.md`.

## Choosing the tool
| Tool | When to use | Notes |
|---|---|---|
| Claude in Chrome (`mcp__claude-in-chrome__*`) | The user's Chrome has a logged-in session | Read the `chrome-browser` skill first. Work in a new tab; do not touch the user's existing tabs |
| Built-in browser (`mcp__Claude_Browser__*` / `mcp__remote-devices__Claude_Browser__*`) | You can log in on the built-in browser side | Read the `built-in-browser` skill first |
| Browser Use (`browser-use` CLI / the browser tool of Codex etc.) | The user's running Chrome has a logged-in session | Read "Cautions for the browser-use CLI" below. Follow the tool's own option for visible / headless. The default is visible |
| Computer Use (`mcp__remote-devices__computer_*` etc.) | There is no browser extension and only screen operation is possible | Read the `computer-use` skill first. Screenshots are per screen, so scroll a long page and take several, numbered `pXXX_s1.png, s2...` |

If headless was requested and the tool does not support headless, tell the user so and continue in visible mode.

## Cautions for the browser-use CLI
- **Name the Chrome to connect to.** Left at the default, it may connect to a different Chrome such as `localhost:9222` (a headless Chrome from some other work, etc.). Have the user allow remote debugging at `chrome://inspect/#remote-debugging` in Chrome, build `BU_CDP_WS=ws://127.0.0.1:<port><path>` from `~/Library/Application Support/Google/Chrome/DevToolsActivePort` (line 1 is the port, line 2 is the path), and pass it every time. If Chrome shows a permission prompt on the first connection, `browser-use mac-approve`.
- Once connected, confirm that `cdp("Browser.getVersion")["userAgent"]` does not contain `HeadlessChrome` and that a tab of the target app (logged in) exists, before starting.
- A Chrome profile cannot be chosen (it connects to the whole running Chrome). If the user names a profile, match the name and account against `profile.info_cache` in `Local State` and tell them which one you take it to be.
- Create exactly one working tab with `new_tab()` and do not touch the user's tabs. Close it with `close_tab()` when done.
- `app-spec-crawler crawl` does all of this automatically (the dedicated connection `BU_NAME=app-spec-crawler`, building `BU_CDP_WS`, the working tab, batched runs, detecting an expired login). What follows is for when you write a script yourself.
- Write the crawl as a Python script and run it with `browser-use < script.py` (the helpers are already loaded). Write the state (queue, visited, pages) to JSON after every page, and make it runnable again and again in batches such as 30 screens at a time (to survive the time limit of a single run).
- Capture only after the screen has finished rendering: wait until the page stops changing (at least the `--wait` time, at most the `--settle-max` time in `bu_crawl.py`), not for a fixed delay alone.
- For a screenshot, first expand the scroll frames inside the screen (elements with `overflow:auto/scroll` whose content is taller than the frame) to the height of their content (`EXPAND` in `bu_crawl.py`; it changes only how the DOM looks), set the width to 1400px and the height to the page height with `Emulation.setDeviceMetricsOverride`, then `capture_screenshot()`. For a screen taller than 6000px, scroll 6000px at a time and capture the continuation as `pXXX_s02.png` …, adding them to `states` as `s02` … (**never cut off because of length or depth**. The cap is 20 images per screen = 120000px; beyond that, leave a line in crawl.log). After capturing, set it back to 1400×900. Capturing works while the tab stays in the background (Chrome is not brought to the front).
- Receive the structure extraction (`EXTRACT`) as a string via `JSON.stringify`, and read the `name` `id` `method` of forms and inputs with `getAttribute()`. In a form that has an input with `name="name"` or `name="id"`, `form.name` returns the input element, the element slips into the result, and CDP fails with `Object reference chain is too long`.
- Apply the same URL rules as `bu_crawl.py` before opening anything: no dangerous keyword, no state-changing token (`_wpnonce`, `csrf_token`, `authenticity_token`, `sesskey` …), no action parameter (`action=`, `do=`, `op=`, `cmd=`, `task=`) with a value that is not read-only.

## Working directory
```
spec_out/
├── pages.json          ← you write it yourself in the schema below (update as you go)
├── screenshots/        ← pXXX.png / pXXX_cNN.png
├── safety_report.json  ← elements not pressed, URLs not opened, errors
└── crawl.log           ← timestamped operation log (everything you pressed)
```

## Procedure
1. Open the start URL and confirm you are logged in. If it is a login screen, ask the user to log in again and stop.
2. Start the **page ledger**: give the current page `p001`, record the URL and title in `pages.json`, and save a full-page screenshot to `screenshots/p001.png`.
3. Read the page structure (use the browser tool's "read the page as text" / DOM retrieval):
   - Headings, navigation, internal links (href and visible text), form input fields (name/type/label/required/placeholder; **do not enter values**), table headers, buttons.
   - Record in `skipped_urls` any internal link containing a dangerous keyword (`deny_url_keywords` in `safety_rules.json`), a state-changing token or a non-read-only action parameter, and do not queue it.
   - Put the remaining unvisited links in the queue (breadth-first). For URLs with an ID such as `/users/123`, keep one representative only.
4. **Click exploration**: list the buttons, tabs, menus, accordions and `role=button` elements, and for each one:
   - Safety check (not matching `deny_click_keywords`, not a submit, has a label, not disabled). If it fails, write the reason in `clickables[].reason` and skip it.
   - **Reload the page to return to the initial state**, then click the element once.
   - Wait, take the screenshot `pXXX_cNN.png`, and record `label / result / url_after / modals` in `states[]`. For `result` use the same fixed English phrases the tools write (`build_book.py` translates them): `Page navigation`, `Modal/dialog shown`, `In-page change`, `No change`.
   - If the modal contains new internal links, add them to the queue.
   - If it navigated, add the destination URL to the queue (unless dangerous) and go back to the original page.
   - When the per-page limit (default 40) is reached, record the rest with a `reason` saying the limit was exceeded.
5. Move to the next URL in the queue and repeat 2–4. When the page limit (default 300) is reached, report to the user.
6. Write out `pages.json` and `crawl.log` at the end of every page (so that the work survives a stop midway).
7. When finished, run `build_book.py --crawl spec_out --init-descriptions` (or `app-spec-crawler describe spec_out --lang <code>`) → write the descriptions → `build_book.py --crawl spec_out` (or `app-spec-crawler build spec_out`), joining `SKILL.md` ②③④. The section tree is generated automatically from the path of `norm_url`, so record URLs with IDs normalized to `{id}`, like `/users/{id}`.

## pages.json schema (same as crawl.py; in a manual crawl, unused fields may be omitted)
```json
{
  "meta": { "start_url": "", "origin": "", "scope": [""], "generated_at": "", "headless": false,
            "click_mode": "safe", "allow_mutations": false, "page_count": 0, "state_count": 0,
            "blocked_request_count": 0, "skipped_element_count": 0, "skipped_url_count": 0, "error_count": 0, "complete": true,
            "method": "manual:claude-in-chrome" },
  "pages": [
    {
      "id": "p001", "url": "https://app.example.com/", "norm_url": "https://app.example.com/", "requested_url": "", "depth": 0, "parent": null,
      "title": "Dashboard", "visited_at": "2026-10-27T10:00:00", "screenshot": "screenshots/p001.png",
      "headings": [{"level": "H1", "text": "Dashboard"}],
      "forms": [{"index": 0, "action": "", "method": "GET", "name": "search",
                 "fields": [{"tag": "input", "type": "text", "name": "q", "id": "", "placeholder": "Search", "required": false, "label": "Keyword"}]}],
      "looseFields": [], "tables": [{"caption": "", "headers": ["ID", "Name"], "rows": 20}], "nav": ["Home Customers Settings"],
      "modals_on_load": [], "bodyText": "(first 40000 characters of the body text)",
      "links": [{"text": "Customers", "href": "https://app.example.com/customers", "internal": true, "norm": "https://app.example.com/customers"},
                {"text": "Log out", "href": "https://app.example.com/logout", "internal": true, "skipped": "Risky URL keyword: logout"}],
      "clickables": [{"index": 0, "tag": "button", "text": "Filter", "ariaLabel": "", "title": "", "role": "", "type": "button",
                      "selector": "#filterBtn", "inForm": false, "disabled": false, "clickable": true, "reason": "ok"},
                     {"index": 1, "tag": "button", "text": "Save", "clickable": false, "reason": "Blocked keyword: save"}],
      "states": [{"id": "c01", "label": "Filter", "selector": "#filterBtn", "role": "button",
                  "result": "Modal/dialog shown", "screenshot": "screenshots/p001_c01.png",
                  "url_after": "https://app.example.com/", "modals": [{"title": "Filter conditions"}], "changed": true}]
    }
  ]
}
```
Text taken from the app (`title`, `headings`, labels, `bodyText`) is recorded as it appears on screen, in the app's language. The fixed phrases (`result`, `reason`) are written in English, as `bu_crawl.py` does.

`safety_report.json`:
```json
{ "blocked_requests": [], "skipped_elements": [{"page": "p001", "text": "Save", "selector": "", "reason": "Blocked keyword: save"}],
  "skipped_urls": [{"page": "p001", "href": "https://app.example.com/logout", "reason": "Risky URL keyword: logout"}], "errors": [] }
```

## Cautions specific to Computer Use
- Capture only the browser window, not the whole screen. Maximize it so that the user's other windows and notifications do not get into the picture.
- Capture a long page while scrolling and name the images `pXXX_s01.png … s0N.png`. Put the first one in `screenshot` and list the rest in `extra_screenshots: []` (`build_book.py` does not support this, so register them as `states` if they need to appear in the book).
- A click-coordinate error can hit the "Save" next to your target. For an element **adjacent** to a state-changing button, zoom in and check the position before clicking, or do not press it.
- Do not type with the keyboard (typing a URL into the address bar is the only exception).
