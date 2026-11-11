#!/usr/bin/env python3
"""The app-spec-crawler command: help / doctor / crawl / describe / build / write / verify.

Runs on the standard library alone. Crawling and the visual check go through browser-use
(the user's own running Chrome).
On an error it prints what happened, why, and how to fix it. It never applies a fix itself;
a person has to approve the fix first.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
NAME = "app-spec-crawler"
BU_NAME = NAME  # a dedicated browser-use connection (daemon), so other browser-use work is not disturbed
CHROME_DIR = Path.home() / "Library/Application Support/Google/Chrome"

sys.path.insert(0, str(SCRIPTS))
try:
    import i18n  # languages of the generated documents (scripts/i18n.py)
except ImportError:  # doctor reports the missing file; commands that need it stop with a clear error
    i18n = None

DOC_LANGS = list(i18n.LANGS) if i18n else ["en", "ja", "zh", "es", "ko"]

DEFAULT_HIDE: list[str] = []  # overlays to hide before a screenshot are passed per target app with --hide
# Text that means "the login has expired" on the target pages. Target apps are often Japanese,
# so the Japanese patterns stay here on purpose.
DEFAULT_SESSION = ["セッションが無効", "セッションの有効期限", "再度ログインしてください", "ログインしてください", "session (has )?expired",
                   "please (log|sign) ?in again"]

# Exit codes
OK, E_GENERAL, E_USAGE, E_SESSION, E_CONNECT, E_DEPENDENCY, E_VERIFY, E_BUILD, E_WRITE = 0, 1, 2, 3, 4, 5, 6, 7, 8
GUIDE_MODEL = "claude-fable-5-1"  # the model that writes the system guide (guide.html)

HELP = f"""\
{NAME} — crawl a web app read-only and build an HTML spec with screenshots

Usage
  {NAME} [help]                       Show this help
  {NAME} doctor [--url URL]           Check that the skill can run now (lists what is missing and how to fix it)
  {NAME} crawl --url URL --out DIR    Crawl the app in your logged-in Chrome (browser-use)
  {NAME} describe DIR [--lang LANG]   Create the template DIR/descriptions.json for the screen descriptions
  {NAME} build DIR                    Build DIR/book/index.html (the screen spec)
  {NAME} write DIR                    Write the system guide DIR/book/guide.html with claude -p (Fable)
  {NAME} verify DIR                   Open the spec in browser-use and check how it looks

Steps
  1. Run doctor. If something is NG it prints how to fix it. Get a person's approval before fixing.
  2. Log in to the target app in your Chrome.
  3. crawl → DIR/pages.json and DIR/screenshots/
  4. describe → Claude looks at the screenshots and fills in descriptions.json
  5. build → write (Fable writes the system guide) → verify → zip DIR/book/ and hand it over

Language of the generated documents
  --lang {{{",".join(DOC_LANGS)}}}   Option of describe. It is stored as "_lang" in descriptions.json,
                            and build and write follow it. Default: the "_lang" already in
                            descriptions.json; otherwise en. A descriptions.json without "_lang"
                            is treated as ja (older projects).
                            build and write also accept --lang to override it for one run.

How the crawl is driven
  browser-use   … First choice. Drives your running, logged-in Chrome without taking over the screen.
  computer-use  … Fallback when browser-use cannot be used. Claude looks at the screen and
                  goes through the app by hand (references/manual-crawl.md).
  Playwright    … Not needed. Use it only when the user asks for it (scripts/crawl.py, optional).

Main crawl options
  --url URL                 Start page (a page you see after logging in)
  --out DIR                 Output folder (a new, empty folder)
  --resume                  Continue a crawl that stopped (after logging in again, pass the new URL as --url)
  --scope-prefix URL        Crawl only URLs that start with this text (default: same origin as the start page)
  --route-param NAME        For apps that switch screens with ?NAME=... (example: page)
  --variant-param NAME      Query parameter that makes a separate screen (example: tab; repeatable)
  --exclude REGEX           URLs not to open (repeatable)
  --allow-route PATH        Screen that may be opened even though its URL has a risky word (example: /export/select)
  --max-pages N / --max-depth N / --batch N
  --wait SECONDS            Minimum wait after a page opens (default 1.0)
  --settle-max SECONDS      Longest time to wait for a page to finish rendering (default 8.0)
  --no-dedupe               Do not merge screens that have identical content
  --no-tabs                 Do not click in-page tabs (#xxx) either
  --retry-errors            Retry the screens that failed last time (use with --resume)
  --relogin CMD             When the login expires, run CMD to log in again and continue
                            (without it the crawl stops with exit code 3)
  --relogin-max N           Maximum number of re-logins (default 3; the crawl stops after that)
  --hide SELECTOR           Overlay to hide before a screenshot (CSS selector of an in-app help
                            panel, a chat widget and so on; repeatable)
  --allow-token-urls        DANGEROUS. Also open URLs that carry a state-changing token
                            (for example a CSRF or one-time action token). Opening such a URL
                            can change data. Use it only when you know these URLs are read-only.

Safety
  Screens are only opened by URL. Nothing is typed, submitted, saved or deleted.
  The only thing clicked is an in-page tab that points to "#xxx".
  URLs that contain logout / delete / approve / export and the like are not opened
  (scripts/safety_rules.json).

Exit codes
  0 success / 1 other error / 2 wrong usage / 3 login expired / 4 cannot connect to Chrome
  5 something required is not installed / 6 the visual check found problems
  7 building the spec failed / 8 writing the guide with Fable failed

The pages always use a light theme (they stay light even when the OS is in dark mode).
"""


def dwidth(t: str) -> int:
    """Display width in a terminal (full-width characters count as 2)."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)


def pad(t: str, w: int) -> str:
    return t + " " * max(0, w - dwidth(t))


class Fail(Exception):
    """An error with three parts: what happened, why, and how to fix it."""

    def __init__(self, code: int, what: str, why: str, fixes: list[str] | None = None, human: bool = True):
        super().__init__(what)
        self.code, self.what, self.why, self.fixes, self.human = code, what, why, fixes or [], human


def report(f: Fail) -> int:
    print(f"\n✖ Error: {f.what}", file=sys.stderr)
    print(f"  Cause: {f.why}", file=sys.stderr)
    if f.fixes:
        print("  How to fix" + (" (get a person's approval before running any of these)" if f.human else "") + ":", file=sys.stderr)
        for i, x in enumerate(f.fixes, 1):
            print(f"    {i}. {x}", file=sys.stderr)
    return f.code


def need_i18n():
    if i18n is None:
        raise Fail(E_DEPENDENCY, "scripts/i18n.py could not be loaded", "The language of the generated documents is defined there",
                   ["Reinstall the skill", f"Run {NAME} doctor again"])
    return i18n


# ---------------------------------------------------------------------------
# Talking to browser-use
# ---------------------------------------------------------------------------
def devtools_ws() -> tuple[str | None, str]:
    """The remote-debugging endpoint of the user's Chrome. Returns (None, reason) when there is none."""
    f = CHROME_DIR / "DevToolsActivePort"
    if not f.exists():
        return None, "Remote debugging is not enabled in Chrome (there is no DevToolsActivePort file)"
    lines = f.read_text().split()
    if len(lines) < 2:
        return None, "The DevToolsActivePort file cannot be read"
    port, path = lines[0], lines[1]
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=2).close()
    except OSError:
        return None, f"Cannot connect to Chrome's remote-debugging port (127.0.0.1:{port}). Chrome was closed, or the permission has expired"
    return f"ws://127.0.0.1:{port}{path}", ""


def need_browser_use() -> str:
    exe = shutil.which("browser-use")
    if not exe:
        raise Fail(E_DEPENDENCY, "browser-use is not installed", "The crawl and the visual check are done with browser-use",
                   ["uv tool install browser-use (if uv is missing: brew install uv)", f"Run {NAME} doctor again"])
    return exe


def run_bu(script: Path, env_extra: dict, timeout: int, first: bool = False) -> str:
    exe = need_browser_use()
    ws, why = devtools_ws()
    if not ws:
        raise Fail(E_CONNECT, "Cannot connect to the user's Chrome", why, [
            "In Chrome, open chrome://inspect/#remote-debugging and turn on \"Allow remote debugging for this browser instance\" (a person does this)",
            f"Run {NAME} doctor again"])
    env = dict(os.environ, BU_NAME=BU_NAME, BU_CDP_WS=ws, **env_extra)
    try:
        with open(script) as fh:
            p = subprocess.run([exe], stdin=fh, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if first:
            raise Fail(E_CONNECT, f"browser-use did not answer within {timeout} seconds",
                       "Chrome is probably still showing the \"Allow remote debugging?\" prompt (it always appears the first time this connection is used)", [
                           "Press \"Allow\" on the prompt in Chrome (a person does this)",
                           f"Or run BU_NAME={BU_NAME} browser-use mac-approve to have the prompt approved",
                           "Run the same command again"])
        raise Fail(E_GENERAL, f"One browser-use run did not finish within {timeout} seconds",
                   "A heavy page never finished loading, or Chrome is not responding",
                   ["Use a smaller --batch and continue with --resume", "Check whether Chrome is frozen"], human=False)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 and "ASC_" not in out:
        tail = "\n      ".join(out.strip().splitlines()[-8:])
        hint = ["Look at the output of browser-use --doctor"]
        if "Allow" in out or "remote debugging" in out.lower():
            hint = ["Press \"Allow\" on the prompt in Chrome (a person does this)", f"Or run BU_NAME={BU_NAME} browser-use mac-approve"]
        raise Fail(E_CONNECT, "browser-use failed to run", f"Last lines of the browser-use output:\n      {tail}", hint)
    return out


def bu_probe() -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write('import json\nv=cdp("Browser.getVersion")\nprint("ASC_PROBE="+json.dumps({"ua":v["userAgent"],"tabs":[t["url"] for t in list_tabs()]}))\n')
    try:
        out = run_bu(Path(fh.name), {}, 40, first=True)
    finally:
        os.unlink(fh.name)
    m = re.search(r"ASC_PROBE=(\{.*\})", out)
    if not m:
        raise Fail(E_CONNECT, "browser-use returned no information about Chrome", "The output has no result: " + out.strip()[-300:],
                   ["Look at the output of browser-use --doctor"])
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
REQUIRED_FILES = ("scripts/build_book.py", "scripts/bu_crawl.py", "scripts/bu_verify.py", "scripts/i18n.py", "scripts/locales/ja.json",
                  "scripts/safety_rules.json", "references/guide-prompt.md")


def cmd_doctor(a) -> int:
    rows: list[tuple[str, str, str, str]] = []  # (OK/NG/WARN/INFO, item, detail, how to fix)

    def add(state, item, detail, fix=""):
        rows.append((state, item, detail, fix))

    v = sys.version_info
    add("OK" if v >= (3, 9) else "NG", "Python", f"{v.major}.{v.minor}.{v.micro} ({sys.executable})", "" if v >= (3, 9) else "Install Python 3.9 or later")
    for f in REQUIRED_FILES:
        if not (SKILL / f).exists():
            add("NG", "Skill files", f"{f} is missing", "Reinstall the skill")
    exe = shutil.which("browser-use")
    if exe:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True)
        add("OK", "browser-use", (r.stdout or r.stderr).strip() or exe)
    else:
        add("NG", "browser-use", "not installed (needed for the crawl and the visual check)", "uv tool install browser-use")
    mac = platform.system() == "Darwin"
    if mac:
        add("OK" if Path("/Applications/Google Chrome.app").exists() else "NG", "Google Chrome",
            "/Applications/Google Chrome.app" if Path("/Applications/Google Chrome.app").exists() else "not found", "Install Google Chrome")
        running = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True).returncode == 0
        add("OK" if running else "NG", "Chrome running", "running" if running else "not running", "Open Chrome and log in to the target app (a person does this)")
        ws, why = devtools_ws()
        add("OK" if ws else "NG", "Chrome remote debugging", ws or why,
            "" if ws else "In Chrome, open chrome://inspect/#remote-debugging and turn on \"Allow remote debugging for this browser instance\" (a person does this)")
        if ws and exe and not a.no_connect:
            try:
                info = bu_probe()
                headless = "Headless" in info["ua"]
                add("NG" if headless else "OK", "browser-use connection",
                    ("connected to a headless Chrome" if headless else "connected to the user's Chrome") + f" ({len(info['tabs'])} tabs)",
                    f"Rebuild the connection with BU_NAME={BU_NAME} browser-use --reload" if headless else "")
                if a.url:
                    origin = re.match(r"https?://[^/]+", a.url)
                    hit = origin and any(t.startswith(origin.group(0)) for t in info["tabs"])
                    add("OK" if hit else "WARN", "Target app tab", "open" if hit else f"no tab for {origin.group(0) if origin else a.url}",
                        "" if hit else "Open the target app in Chrome and log in (a person does this)")
            except Fail as f:
                add("NG", "browser-use connection", f.what + ". " + f.why.split("\n")[0], " / ".join(f.fixes))
    else:
        add("WARN", "OS", f"{platform.system()} (the Chrome remote-debugging check only supports macOS)", "Check with browser-use --doctor")
    cl = shutil.which("claude")
    add("OK" if cl else "NG", "claude (write)", (cl + f" (writes the system guide with {GUIDE_MODEL})") if cl else "not installed (used by write)",
        "" if cl else "Install Claude Code (npm install -g @anthropic-ai/claude-code)")
    add("INFO", "computer-use", "a tool on Claude's side, so this command cannot check it. It is the fallback when browser-use cannot be used", "")
    try:
        import importlib.util
        pw = importlib.util.find_spec("playwright") is not None
    except Exception:
        pw = False
    add("INFO", "Playwright", ("installed" if pw else "not installed") + " (not needed; only for scripts/crawl.py)", "")
    add("OK" if shutil.which("zip") else "WARN", "zip", "found" if shutil.which("zip") else "not found (needed to hand over the spec as a zip)",
        "" if shutil.which("zip") else "Install zip")

    w = max(dwidth(r[1]) for r in rows) + 2
    mark = {"OK": "✔", "NG": "✖", "WARN": "!", "INFO": "·"}
    print(f"{NAME} doctor\n")
    for s, item, detail, _ in rows:
        print(f"  {mark[s]} {pad(s, 5)}{pad(item, w)}{detail}")
    ng = [r for r in rows if r[0] == "NG"]
    warn = [r for r in rows if r[0] == "WARN"]
    fixes = [r for r in rows if r[0] in ("NG", "WARN") and r[3]]
    if fixes:
        print("\nHow to fix (get a person's approval before running any of these):")
        for i, (_, item, _, fix) in enumerate(fixes, 1):
            print(f"  {i}. [{item}] {fix}")
    print("\nResult: " + ("ready" if not ng and not warn else "ready (with warnings)" if not ng else f"not ready ({len(ng)} NG)"))
    if ng:
        connect = any(r[1].startswith(("Chrome", "browser-use connection")) for r in ng)
        return E_CONNECT if connect and not any(r[1] in ("browser-use", "Python") for r in ng) else E_DEPENDENCY
    return OK


# ---------------------------------------------------------------------------
# crawl
# ---------------------------------------------------------------------------
def cmd_crawl(a) -> int:
    out = Path(a.out).expanduser().resolve()
    state = out / "state.json"
    if state.exists() and not a.resume:
        raise Fail(E_USAGE, f"{out} still holds an unfinished crawl", "Stopped because overwriting it would lose the earlier result",
                   ["Add --resume to continue it", "Pass a different --out to start over"], human=False)
    if out.exists() and any(out.iterdir()) and not state.exists():
        raise Fail(E_USAGE, f"{out} is not an empty folder", "The crawl result must not get mixed with other files",
                   ["Pass a new, empty folder as --out"], human=False)
    if not re.match(r"https?://", a.url or ""):
        raise Fail(E_USAGE, "--url does not start with http(s)://", f"Value received: {a.url!r}",
                   ["Pass the URL of a page you see after logging in as --url"], human=False)
    out.mkdir(parents=True, exist_ok=True)
    origin = re.match(r"https?://[^/]+", a.url).group(0)
    # The config that bu_crawl.py reads (through the ASC_CONFIG environment variable)
    cfg = {"url": a.url, "url_display": a.url, "out": str(out), "rules": str(SCRIPTS / "safety_rules.json"),
           "scope_prefix": a.scope_prefix or origin, "scope_display": a.scope_prefix or origin,
           "route_param": a.route_param, "variant_params": a.variant_param, "exclude": a.exclude, "allow_routes": a.allow_route,
           "extra_deny": a.extra_deny, "hide_selectors": DEFAULT_HIDE + a.hide, "session_error_patterns": DEFAULT_SESSION + a.session_text,
           "tabs": not a.no_tabs, "keep_query": a.keep_query, "id_collapse": not a.no_id_collapse,
           "retry_errors": a.retry_errors, "run_id": f"{os.getpid()}-{int(time.time())}", "batch": a.batch, "max_pages": a.max_pages,
           "max_depth": a.max_depth, "wait": a.wait, "settle_max": a.settle_max, "dedupe": not a.no_dedupe,
           "allow_token_urls": a.allow_token_urls}
    cfg_path = out / "crawl_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    print(f"Starting the crawl: {a.url}\n  Output: {out}\n  {a.batch} screens per run, at most {a.max_pages} screens. The crawl stops if the login expires.")
    if a.allow_token_urls:
        print("  ! --allow-token-urls is on: URLs that carry a state-changing token will be opened. This can change data.")
    first = True
    relogins = 0
    for _ in range(1000):
        res = run_bu(SCRIPTS / "bu_crawl.py", {"ASC_CONFIG": str(cfg_path)}, 600, first=first)
        first = False
        for line in res.splitlines():
            if re.match(r"p\d{3} |ERROR ", line):
                print("  " + line)
        m = re.search(r"ASC_STATUS=(\w+) ?(.*)", res)
        if not m:
            tail = "\n      ".join(res.strip().splitlines()[-10:])
            raise Fail(E_GENERAL, "The crawl script crashed", f"Last lines of the output:\n      {tail}",
                       [f"Continue with {NAME} crawl ... --resume", "If it keeps crashing on the same screen, leave that URL out with --exclude"], human=False)
        status, msg = m.group(1), m.group(2)
        if status == "more":
            print(f"  … {msg}")
            continue
        if status == "done":
            s = json.loads(state.read_text())
            print(f"\n✔ Crawl finished ({msg})\n  Screens {len(s['pages'])} / URLs not opened {len(s['skipped_urls'])} / elements not clicked {len(s['skipped_elements'])} / errors {len(s['errors'])}")
            print(f"  Next: {NAME} describe {out}")
            return OK
        if status in ("session", "start_failed") and a.relogin and relogins < a.relogin_max:
            relogins += 1
            print(f"  ! The login expired ({msg}). Logging in again with --relogin (attempt {relogins} of {a.relogin_max})")
            env = dict(os.environ, ASC_OUT=str(out), ASC_URL=a.url, BU_NAME=BU_NAME)
            ws, _ = devtools_ws()
            if ws:
                env["BU_CDP_WS"] = ws
            try:
                r = subprocess.run(a.relogin, shell=True, env=env, capture_output=True, text=True, timeout=a.relogin_timeout)
            except subprocess.TimeoutExpired:
                raise Fail(E_SESSION, "The re-login did not finish in time",
                           f"The --relogin command did not finish within {a.relogin_timeout} seconds (for example, it is waiting for a 1Password approval)", [
                               "If an approval prompt is showing, approve it, then run the same command again with --resume"])
            if r.returncode != 0:
                tail = "\n      ".join((r.stdout + r.stderr).strip().splitlines()[-6:])
                raise Fail(E_SESSION, "The re-login failed", f"The --relogin command ended with exit code {r.returncode}:\n      {tail}", [
                    "Log in to the target app again in Chrome (a person does this)", f"Continue with {NAME} crawl ... --resume"])
            print("  ✔ Logged in again. Continuing the crawl")
            continue
        if status in ("session", "start_failed"):
            raise Fail(E_SESSION, "The login has expired" if status == "session" else "The start page did not open in a logged-in state", msg, [
                "Log in to the target app again in Chrome (a person does this)",
                f"Run {NAME} crawl --url <new URL> --out {out} --resume with the URL you see after logging in (the crawl continues even if the token in the URL changed)"])
        raise Fail(E_GENERAL, "The crawl stopped", msg, [f"Continue with {NAME} crawl ... --resume"], human=False)
    return OK


# ---------------------------------------------------------------------------
# describe / build / write / verify
# ---------------------------------------------------------------------------
def crawl_dir(d: str) -> Path:
    p = Path(d).expanduser().resolve()
    if not (p / "pages.json").exists():
        raise Fail(E_USAGE, f"There is no pages.json in {p}", "This is not a crawl output folder, or the crawl has not finished",
                   [f"Crawl the app with {NAME} crawl", "Pass the folder you used as --out for the crawl"], human=False)
    return p


def run_build(args: list[str]) -> str:
    p = subprocess.run([sys.executable, str(SCRIPTS / "build_book.py")] + args, capture_output=True, text=True)
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip()
        why = err.splitlines()[-1] if err else "unknown"
        fixes = ["Read the error line and fix the file it points to"]
        if "JSONDecodeError" in err:
            fixes = ["descriptions.json is not valid JSON. Find the place with python3 -m json.tool DIR/descriptions.json and fix it"]
        raise Fail(E_BUILD, "Building the spec failed", why, fixes, human=False)
    return p.stdout


def desc_lang(d: Path) -> str:
    """Language of the generated documents: the "_lang" in descriptions.json.

    A descriptions.json without "_lang" is an older project, and those are Japanese ("ja").
    When there is no descriptions.json yet, the language is English ("en").
    """
    f = d / "descriptions.json"
    if not f.exists():
        return "en"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("_lang") or "ja"
    except (OSError, ValueError, AttributeError):
        return "ja"


def lang_args(a) -> list[str]:
    """The --lang override to pass through to build_book.py (nothing when the option was not given)."""
    lang = getattr(a, "lang", None)
    return ["--lang", lang] if lang else []


def cmd_describe(a) -> int:
    d = crawl_dir(a.dir)
    lang = a.lang or desc_lang(d)  # keep the language of an existing descriptions.json; a new one is English
    print(run_build(["--crawl", str(d), "--init-descriptions", "--lang", lang]).strip())
    name = i18n.language_name(lang) if i18n else lang
    print(f"Next: fill in {d}/descriptions.json in {name} (see references/description-guide.md) → {NAME} build {d}")
    return OK


def cmd_build(a) -> int:
    d = crawl_dir(a.dir)
    print(run_build(["--crawl", str(d)] + lang_args(a)).strip())
    print(f"Next: {NAME} write {d} (Fable writes the system guide) → {NAME} verify {d}")
    return OK


GUIDE_KEEP = ("name", "category", "summary", "purpose", "users_and_usage", "display_conditions", "features", "flows",
              "business_rules", "open_questions", "specs")


def guide_material(d: Path, book: Path) -> str:
    """The material handed to Fable: the description fields the guide needs, and the list of files it may link to."""
    desc = json.loads((d / "descriptions.json").read_text(encoding="utf-8"))
    crawl = json.loads((d / "pages.json").read_text(encoding="utf-8"))
    pages = []
    for pg in crawl["pages"]:
        x = {k: v for k, v in desc.get("pages", {}).get(pg["id"], {}).items() if k in GUIDE_KEEP and v}
        for sp in x.get("specs") or []:
            for k in ("evidence", "notes"):
                sp.pop(k, None)
        pages.append({"id": pg["id"], "path": re.sub(r"^https?://[^/]+", "", pg.get("norm_url", "")), **x})
    secs = {p: {k: v for k, v in s.items() if not k.startswith("_") and v} for p, s in desc.get("sections", {}).items()}
    files = sorted(str(f.relative_to(book)) for f in book.rglob("*") if f.suffix in (".html", ".png") and f.name != "guide.html"
                   and not f.relative_to(book).parts[0] == "assets")
    files = [f for f in files if not re.match(r"screenshots/p\d+_", f)]  # leave out the click-state images to keep the material small
    return json.dumps({"app": desc.get("app", {}), "sections": secs, "pages": pages, "available_files": files}, ensure_ascii=False, indent=0)


def guide_prompt(lang: str) -> str:
    """The one English prompt for every language, with the language name and the three confidence labels filled in."""
    tr = need_i18n()
    f = SKILL / "references" / "guide-prompt.md"
    try:
        text = f.read_text(encoding="utf-8")
    except OSError as e:
        raise Fail(E_DEPENDENCY, "references/guide-prompt.md cannot be read", str(e), ["Reinstall the skill"])
    if "{{LANGUAGE}}" not in text:
        raise Fail(E_DEPENDENCY, "references/guide-prompt.md has no {{LANGUAGE}} placeholder",
                   "The prompt file is from an older version of the skill, so the guide could come out in the wrong language", ["Reinstall the skill"])
    for key, value in (("{{LANGUAGE}}", tr.language_name(lang)), ("{{VERIFIED}}", tr.confidence_label(lang, "verified")),
                       ("{{INFERRED}}", tr.confidence_label(lang, "inferred")), ("{{TO_CONFIRM}}", tr.confidence_label(lang, "to_confirm"))):
        text = text.replace(key, value)
    return text


def clean_guide(html: str, book: Path) -> tuple[str, list[str]]:
    """Remove unsafe markup and links to missing files from Fable's output. Also returns the list of what was changed."""
    notes = []
    m = re.search(r"<article class=\"guide\".*</article>", html, re.S)
    if not m:
        raise Fail(E_WRITE, "Fable's output has no <article class=\"guide\">",
                   "It was not written in the requested form (cut off part-way, only an explanation came back, and so on)",
                   ["Run write again", "If it keeps happening, raise --budget"], human=False)
    html = m.group(0)
    for pat, what in ((r"<(script|style|iframe)\b.*?</\1>", "script/style block(s)"), (r"\s(on\w+|style)=\"[^\"]*\"", "attribute(s)")):
        html, n = re.subn(pat, "", html, flags=re.S | re.I)
        if n:
            notes.append(f"removed {n} {what}")

    def fix(m_):
        attr, val = m_.group(1), m_.group(2)
        target = val.split("#")[0]
        if val.startswith("#") or (target and (book / target).exists()):
            return m_.group(0)
        notes.append(f"removed {'an image' if attr == 'src' else 'a link'} that points to a missing file: {val}")
        return f'{attr}="#"' if attr == "href" else 'src="" hidden'
    html = re.sub(r'\b(href|src)="([^"]*)"', fix, html)
    return html, notes


def cmd_write(a) -> int:
    d = crawl_dir(a.dir)
    book = d / "book"
    if not (book / "index.html").exists():
        raise Fail(E_USAGE, "The screen spec does not exist yet",
                   f"{book}/index.html is missing. The system guide links to the images and pages of the screen spec, so build has to run first",
                   [f"{NAME} build {d}"], human=False)
    if not (d / "descriptions.json").exists():
        raise Fail(E_USAGE, "descriptions.json is missing", "Fable uses the screen descriptions written by Claude as its material",
                   [f"Run {NAME} describe {d}, then fill in descriptions.json"], human=False)
    todo = (d / "descriptions.json").read_text(encoding="utf-8").count('"specs": []')
    if todo:
        print(f"! {todo} screen(s) have no spec items. The guide will say little about them")
    exe = shutil.which("claude")
    if not exe:
        raise Fail(E_DEPENDENCY, "claude (Claude Code) is not installed", "The system guide is written by Fable through claude -p",
                   ["npm install -g @anthropic-ai/claude-code", "Log in to claude (a person does this)", f"Run {NAME} doctor again"])
    lang = a.lang or desc_lang(d)
    prompt = guide_prompt(lang) + "\n" + guide_material(d, book)
    cmd = [exe, "-p", "--model", a.model, "--tools", "", "--permission-mode", "dontAsk", "--max-budget-usd", str(a.budget), "--effort", "high"]
    print(f"Asking {a.model} to write the guide in {i18n.language_name(lang)} "
          f"(material: {len(prompt) // 1000}k characters; this takes a few minutes; budget limit ${a.budget}) …")
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=a.timeout, cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        raise Fail(E_WRITE, f"Fable did not finish writing within {a.timeout} seconds", "There is a lot of material, or the service is busy",
                   ["Run write again with a longer --timeout"], human=False)
    out = p.stdout or ""
    if p.returncode != 0 or "<article" not in out:
        err = (p.stderr or out).strip()
        last = err.splitlines()[-1] if err else f"exit code {p.returncode}, no output"
        fixes = ["Run write again"]
        if re.search(r"budget", err, re.I):
            fixes = [f"Raise --budget (now ${a.budget}; this costs money, so get a person's approval)"]
        elif re.search(r"log ?in|auth|credential|401", err, re.I):
            fixes = ["Log in to claude again (start claude in a terminal and run /login; a person does this)"]
        elif re.search(r"model", err, re.I):
            fixes = ["Change --model (example: --model opus)", "See the --model entry of claude --help for the models you can use"]
        raise Fail(E_WRITE, "Writing the guide with Fable failed", last, fixes)
    body, notes = clean_guide(out, book)
    (d / "guide_body.html").write_text(f"<!-- model: {a.model} -->\n{body}\n", encoding="utf-8")
    run_build(["--crawl", str(d)] + lang_args(a))  # wraps the body (guide_body.html) into book/guide.html and links it from the screen spec
    print(f"✔ Written: {book}/guide.html ({len(body) // 1000}k characters)")
    for n in notes:
        print("  Changed: " + n)
    print("  Fable sometimes adds facts that are not in the material. Check the numbers, screen names and button names against the material")
    print(f"Next: {NAME} verify {d}")
    return OK


def cmd_verify(a) -> int:
    d = crawl_dir(a.dir)
    book = d / "book"
    if not (book / "index.html").exists():
        raise Fail(E_USAGE, "The spec does not exist yet", f"{book}/index.html is missing", [f"{NAME} build {d}"], human=False)
    # Unfilled placeholders are counted by their markup, so the count works in every language
    todo = sum(f.read_text(encoding="utf-8").count('class="todo"') for f in book.rglob("*.html"))
    shots = d / "verify"
    cfg = Path(tempfile.mkstemp(suffix=".json")[1])
    cfg.write_text(json.dumps({"book": str(book), "shots": str(shots)}))
    try:
        res = run_bu(SCRIPTS / "bu_verify.py", {"ASC_CONFIG": str(cfg)}, 300, first=True)
    finally:
        cfg.unlink()
    m = re.search(r"ASC_VERIFY=(\{.*\})", res)
    if not m:
        raise Fail(E_GENERAL, "The visual check crashed", res.strip()[-400:], ["Run it again"], human=False)
    r = json.loads(m.group(1))
    problems = r["problems"] + ([f"{todo} unfilled placeholder(s) remain (class=\"todo\")"] if todo else [])
    print(f"Pages checked: {', '.join(r['pages'])}\nScreenshots: {shots}/ ({len(r['shots'])} images, widths 1440/390, "
          "taken with the OS dark mode emulated to confirm the pages stay light)")
    if problems:
        print("\n✖ Problems found:")
        for x in problems:
            print("  - " + x)
        print("\nHow to fix: for overflow and images, fix assets/book.css or scripts/build_book.py; for unfilled placeholders, "
              "fill in descriptions.json; then build again (get a person's approval before changing the skill itself)")
        return E_VERIFY
    print("✔ No overflow, broken images, dark backgrounds or unfilled placeholders were found. "
          "Look at the screenshots yourself as well, and check table wrapping and overlaps")
    return OK


# ---------------------------------------------------------------------------
def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keeps errors (stderr) and progress lines in the right order
    if len(sys.argv) == 1 or sys.argv[1] in ("help", "-h", "--help"):
        print(HELP)
        return OK

    class Parser(argparse.ArgumentParser):
        def error(self, message):  # turn argparse's own error into a Fail that states the cause
            m = re.search(r"required: (.+)", message)
            why = f"The required argument {m.group(1)} is missing" if m else f"argparse says: {message}"
            raise Fail(E_USAGE, f"The arguments of \"{' '.join(sys.argv[1:])}\" are incomplete or wrong", why,
                       [f"See {NAME} help for the syntax"], human=False)

    ap = Parser(prog=NAME, add_help=False)
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("doctor")
    d.add_argument("--url", help="also check that a tab of this app is open")
    d.add_argument("--no-connect", action="store_true", help="skip the trial connection through browser-use")
    c = sub.add_parser("crawl")
    c.add_argument("--url", required=True, help="start page (a page you see after logging in)")
    c.add_argument("--out", required=True, help="output folder (new and empty)")
    c.add_argument("--resume", action="store_true", help="continue a crawl that stopped")
    c.add_argument("--scope-prefix", help="crawl only URLs that start with this text (default: same origin as --url)")
    c.add_argument("--route-param", help="query parameter that switches screens (?NAME=...)")
    c.add_argument("--variant-param", action="append", default=[], help="query parameter that makes a separate screen (repeatable)")
    c.add_argument("--exclude", action="append", default=[], help="regular expression of URLs not to open (repeatable)")
    c.add_argument("--allow-route", action="append", default=[], help="path that may be opened even though it has a risky word (repeatable)")
    c.add_argument("--extra-deny", action="append", default=[], help="extra word that marks a URL as risky (repeatable)")
    c.add_argument("--hide", action="append", default=[], help="CSS selector of an overlay to hide before a screenshot (repeatable)")
    c.add_argument("--session-text", action="append", default=[], help="extra text (regular expression) that means the login has expired (repeatable)")
    c.add_argument("--no-tabs", action="store_true", help="do not click in-page tabs (#xxx)")
    c.add_argument("--keep-query", action="store_true", help="treat URLs with different query strings as separate screens")
    c.add_argument("--no-id-collapse", action="store_true", help="do not treat /items/1 and /items/2 as the same screen")
    c.add_argument("--batch", type=int, default=30, help="screens per browser-use run")
    c.add_argument("--max-pages", type=int, default=300, help="maximum number of screens")
    c.add_argument("--max-depth", type=int, default=10, help="maximum link depth from the start page")
    c.add_argument("--wait", type=float, default=1.0, help="minimum wait in seconds after a page opens")
    c.add_argument("--settle-max", type=float, default=8.0, help="longest time in seconds to wait for a page to finish rendering")
    c.add_argument("--no-dedupe", action="store_true", help="do not merge screens that have identical content")
    c.add_argument("--allow-token-urls", action="store_true",
                   help="DANGEROUS: also open URLs that carry a state-changing token. Opening such a URL can change data")
    c.add_argument("--retry-errors", action="store_true", help="retry the screens that failed last time (use with --resume)")
    c.add_argument("--relogin", help="command to run when the login expires (exit code 0 means logged in again; the crawl then continues)")
    c.add_argument("--relogin-max", type=int, default=3, help="maximum number of re-logins; the crawl stops after that")
    c.add_argument("--relogin-timeout", type=int, default=180, help="seconds to wait for the --relogin command")
    lang_help = "language of the generated documents"
    sp = sub.add_parser("describe")
    sp.add_argument("dir")
    sp.add_argument("--lang", choices=DOC_LANGS,
                    help=lang_help + " (default: the _lang already in descriptions.json, otherwise en). Stored as _lang in descriptions.json; build and write follow it")
    sp = sub.add_parser("build")
    sp.add_argument("dir")
    sp.add_argument("--lang", choices=DOC_LANGS, help=lang_help + " for this run (default: the _lang in descriptions.json)")
    sub.add_parser("verify").add_argument("dir")
    w = sub.add_parser("write")
    w.add_argument("dir")
    w.add_argument("--lang", choices=DOC_LANGS, help=lang_help + " for this run (default: the _lang in descriptions.json)")
    w.add_argument("--model", default=GUIDE_MODEL, help="model that writes the system guide")
    w.add_argument("--budget", type=float, default=8.0, help="spending limit for claude -p, in US dollars")
    w.add_argument("--timeout", type=int, default=1800, help="seconds to wait for the model")
    if sys.argv[1] not in ("doctor", "crawl", "describe", "build", "write", "verify"):
        return report(Fail(E_USAGE, f"Unknown command \"{sys.argv[1]}\"", "The commands are help / doctor / crawl / describe / build / write / verify",
                           [f"See {NAME} help for how to use it"], human=False))
    try:
        a = ap.parse_args()
        return {"doctor": cmd_doctor, "crawl": cmd_crawl, "describe": cmd_describe, "build": cmd_build, "write": cmd_write, "verify": cmd_verify}[a.cmd](a)
    except Fail as f:
        return report(f)
    except KeyboardInterrupt:
        return report(Fail(E_GENERAL, "Stopped part-way", "Ctrl+C was pressed", ["To continue a crawl, add --resume to crawl"], human=False))


if __name__ == "__main__":
    sys.exit(main())
