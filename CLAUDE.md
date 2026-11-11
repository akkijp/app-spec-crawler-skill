# app-spec-crawler — notes for Claude Code

A Claude Code skill: it crawls a web app the user is logged into (read-only), screenshots every screen, and has Claude write a screen spec and a system guide. `SKILL.md` is the procedure; `README.md` is the public face.

## Language

- English is the base language of this repository: code, comments, CLI output, `SKILL.md`, `references/`, `docs/`, `README.md`.
- Japanese copies live in `README.ja.md` and `docs/ja/`. When you change an English doc, update its Japanese copy in the same commit.
- **Write git commit messages in English.** Use an imperative subject line of about 70 characters or less, then a body that says what changed and why. (Commits before v1.0.0 are in Japanese; do not rewrite history.)
- Pull request titles and descriptions, release notes and issue replies are in English too.
- Talk to the user in the language they are using.

## Versions and releases

- Releases follow `MAJOR.MINOR.PATCH`, tagged `vX.Y.Z`, published as GitHub releases. The first release is `v1.0.0`.
- **Raise MINOR for every release that adds or changes a feature** (1.0.0 → 1.1.0 → 1.2.0). This is the normal case.
- Raise PATCH for a release that only fixes bugs or documentation (1.1.0 → 1.1.1).
- Raise MAJOR only when an existing way of using the skill stops working (a removed flag, a changed output format that old books cannot be built from).
- Release from `main` after the change has been merged through a pull request. Write the release notes in English: what is new, what changed for existing users, known limits.
- Do not create a release unless the user asks for one.

## Things that must stay true

- **Read-only.** The crawler never types, never submits a form, and never clicks anything except in-page tabs. Do not add code that does. `references/safety-policy.md` is the rule book.
- **Japanese output must not change by accident.** A project without `_lang` in `descriptions.json` is treated as Japanese; `scripts/locales/ja.json` reproduces the wording from before the i18n change.
- **Every UI string in the generated book goes through `i18n.t()`**, and every key exists in all catalogs under `scripts/locales/`.
- **Say only what was measured.** Numbers in the README (screens, time, cost) come from real runs; say what was measured and on what.
- **No media in the repository.** Videos go on GitHub as attachments (drag into the editor); the sample output lives in `akkijp/app-spec-crawler-examples`.

## Before a pull request

- `python3 -m py_compile scripts/*.py` and `app-spec-crawler doctor --no-connect`.
- If `build_book.py` or a catalog changed: build an existing Japanese project with the old and the new code and diff the HTML.
- If the crawl changed: run it against a disposable test app and confirm the app's data is unchanged afterwards.
