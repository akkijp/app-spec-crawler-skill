# Safety policy (read-only crawl)

Work on the assumption that the target is a production system the customer uses for their business.
"Even one record changes", "even one notification goes out" or "the session is cut" is real harm to the user and to their customer.
Safety comes before coverage. When in doubt, do not press and do not proceed.

## Prohibitions (hard rules)
1. Do not press any button, link or menu item containing save / register / update / send / submit / confirm / decide / apply / reflect / run / delete / discard / approve / reject / publish / post / issue / purchase / pay / order / sign up / contract / cancel a contract / withdraw / invite / import / upload / sync / reset / initialize / enable or disable / archive / restore / log out and the like — in any language. In a Japanese UI these are words such as 「保存」「登録」「更新」「送信」「確定」「削除」「承認」「公開」「ログアウト」.
2. Do not enter, select or change a value in a form (search boxes included; checkboxes, toggles and drag & drop also count as changes).
3. Do not choose, upload or download files.
4. Always answer confirmation dialogs (confirm / prompt / beforeunload / "OK" or "Yes" in the app's own modal) with "Cancel" or "No".
5. Do not navigate to a URL containing `logout` `delete` `destroy` `remove` `revoke` `approve` `publish` `export` `download` `run` `execute` and the like.
6. Do not navigate to a URL that carries a state-changing token or a non-read-only action parameter (see "Protections of the browser-use crawl", rule 3).
7. Do not navigate to an external site (another origin).
8. For administrator bulk operations, batch runs, email sending and notification sending screens: go only as far as opening the screen.
9. Do not use `--allow-mutations` or `--allow-token-urls`, except on your own test environment when the user explicitly asks for it.

## Protections of the browser-use crawl (`app-spec-crawler crawl`, the default)
The crawl opens screens by URL (GET) and nothing else. On top of that:

1. **No input, no submit.** The code contains nothing that types into a field, selects a value, chooses a file or submits a form.
2. **Dangerous URL keywords.** A URL whose path or query contains a keyword in `deny_url_keywords` of `scripts/safety_rules.json` (`logout`, `delete`, `approve`, `export`, `download` …) is not opened.
3. **State-changing tokens and action parameters.** Some apps change data on a plain GET link — in WordPress, "Trash" and "Activate" are ordinary links. So by default the crawler refuses to open:
   - any URL that carries a state-changing token: a query parameter such as `_wpnonce`, `csrf_token`, `authenticity_token`, `sesskey`;
   - any URL with an action parameter (`action=`, `do=`, `op=`, `cmd=`, `task=`) whose value is not a known read-only one (`edit`, `view`, `show`, `list`, `search` …).
4. **Scope.** A URL outside the scope (another origin, or outside `--scope-prefix`) is not opened.
5. **Clicks.** The only click is on an in-page tab pointing at `#name` on the current page, which sends nothing to the server (`--no-tabs` turns it off). Buttons are recorded, not pressed.
6. **Login.** When the login has expired the crawl stops (exit code 3) instead of capturing or operating the login screen.
7. **The user's tabs.** The crawl works in one tab of its own and does not touch the tabs the user has open.

Every URL that was not opened is listed in `safety_report.json` under `skipped_urls`, with the reason.

Exceptions, and when they are allowed:
- `--allow-route PATH` re-admits one specific screen. Use it only after looking at what the URL is and confirming with the user that it only displays something.
- `--allow-token-urls` disables rule 3 entirely. It is dangerous: a single link carrying a nonce can delete or activate something. Use it only when the user explicitly asks for it on a test system. Never on a customer's production system.

**What these protections cannot do.** An app can change something merely because a page was opened, with no token and no action parameter in the URL. WordPress, for example, creates an auto-draft every time the "Add Post" screen loads. The crawler cannot know this. Exclude such screens with `--exclude` when they are known, and ask the user about them before crawling.

## Five layers of protection in crawl.py (enforced by the program)
| Layer | What it does | Implementation |
|---|---|---|
| Network | Blocks every HTTP request other than GET / HEAD / OPTIONS and logs it | `abort` in `context.route("**/*")` |
| Element | Does not click forbidden keywords, `type=submit/reset`, a button with no type inside a form, or an element with no label | `element_click_verdict()` |
| Input | Never calls an input API (`fill` / `type` / `select_option` / `set_input_files` are not used) | Does not exist in the code |
| Dialog | `dismiss()` (= cancel) on everything via `page.on("dialog")` | `install_dialog_guard()` |
| Navigation | URLs containing a dangerous keyword and out-of-scope URLs are not queued | `url_is_dangerous()` / `url_in_scope()` |

In addition, each click is made **exactly once, from the initial state after reloading the page every time**. States do not mix, results are deterministic, and
the accident of "the next click presses the Save button inside the modal the previous click opened" is prevented by construction.

The network layer is the last line of defense. Even if a Save button slips past the element check and is pressed, POST/PUT/PATCH/DELETE never reach the server.
But it does **nothing against a badly behaved app that causes side effects on GET** (`?action=delete` etc.), which is why the URL keyword check is used alongside it.
Add the target app's own dangerous paths to `deny_url_keywords` in `safety_rules.json` beforehand.

## Additional rules for a manual (AI-operated) crawl
- Before clicking, read the element's label, aria-label and surrounding context and decide whether it displays or changes something. If it changes something, do not press. Leave the decision in the log (`clickables[].reason` in `pages.json`).
- Do not press a button that has only an icon and no label (purpose unknown).
- After opening a modal, the only ways to close it are "×", "Close", Esc, or a click outside the modal. Do not close it with "OK", "Save" or "Apply".
- Expanding tabs, accordions and dropdowns is allowed. But do not press a state-changing button that appears inside.
- Pagination such as "Next" and "Show more" is allowed (display only).
- Before following a link, apply the same URL rules as the crawler: no dangerous keyword, no state-changing token, no non-read-only action parameter.
- After a navigation, confirm that the destination is not a dangerous URL before continuing.
- When the work on one page is done, always return to the initial state (reload) before moving to the next element.

## If you think an accident happened
Stop operating immediately. Write what you pressed, at which URL and at what time into `crawl.log` (or the manual log), and report to the user.
Do not hide it. Do not attempt recovery yourself either (an update to put things back is still an update).
