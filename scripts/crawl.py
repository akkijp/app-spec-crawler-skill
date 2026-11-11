#!/usr/bin/env python3
"""
app-spec-crawler / crawl.py
---------------------------
Optional Playwright crawler. Uses a logged-in browser profile (or a CDP connection to a running Chrome)
to crawl a web application under a given URL in read-only mode, and writes screenshots of every page
and every "safe click state" together with the structure data (pages.json).

Absolute rule: never change any data of the application.
  1. Network:   every HTTP request other than GET/HEAD/OPTIONS is blocked (default)
  2. Elements:  elements with keywords such as save/delete/send, and submit-type elements, are never clicked
  3. Input:     nothing is typed into forms and no file is selected
  4. Dialogs:   confirm/prompt/beforeunload are all dismissed (= cancelled)
  5. Navigation: URLs that contain logout/delete and the like are not opened

Usage (examples):
  python crawl.py --url https://app.example.com/ --profile "/Users/me/Library/Application Support/Google/Chrome" \
      --profile-directory "Profile 1" --out ./out
  python crawl.py --url https://app.example.com/ --cdp http://localhost:9222 --out ./out   # attach to a running Chrome
  python crawl.py --url ... --storage-state state.json --out ./out                          # saved Playwright state
  Option: --headless runs without a window (default: the window is shown)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import traceback
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    print("playwright was not found: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ----------------------------------------------------------------------------
# Arguments
# ----------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only web app crawl and screenshot collection")
    p.add_argument("--url", required=True, help="start URL of the crawl")
    p.add_argument("--out", default="./out", help="output directory")

    g = p.add_argument_group("Browser / authentication (choose one)")
    g.add_argument("--profile", help="browser user data directory (Chrome/Edge/Chromium). It cannot be used while a browser is running on that profile, so passing a copy is the safe way")
    g.add_argument("--profile-directory", default=None, help="profile name inside --profile (examples: 'Default', 'Profile 1')")
    g.add_argument("--cdp", help="CDP endpoint of a running browser (example: http://localhost:9222). Start it with chrome --remote-debugging-port=9222")
    g.add_argument("--storage-state", help="Playwright storage_state JSON")
    g.add_argument("--channel", default=None, help="chrome / msedge / chromium (default: chrome with --profile, otherwise chromium)")

    s = p.add_argument_group("Crawl scope")
    s.add_argument("--scope-prefix", action="append", default=[], help="crawl only under this URL prefix (repeatable). Default: the whole origin of the start URL")
    s.add_argument("--exclude", action="append", default=[], help="regular expression of URLs to exclude (repeatable)")
    s.add_argument("--max-pages", type=int, default=300)
    s.add_argument("--max-depth", type=int, default=10)
    s.add_argument("--keep-query", action="store_true", help="treat different query strings as separate pages (default: ignored)")
    s.add_argument("--id-collapse", action="store_true", help="treat numeric ID segments such as /users/123 as the same page and crawl one representative only")

    c = p.add_argument_group("Click exploration")
    c.add_argument("--click-mode", choices=["safe", "none"], default="safe", help="safe: click only elements that pass the safety check / none: click nothing")
    c.add_argument("--max-clicks-per-page", type=int, default=40)
    c.add_argument("--click-allow-pattern", help="click only elements whose text matches this regular expression (narrows further)")

    d = p.add_argument_group("Display and waiting")
    d.add_argument("--headless", action="store_true", help="run headless (default: the window is shown)")
    d.add_argument("--viewport", default="1440x900")
    d.add_argument("--wait", type=int, default=1200, help="extra wait after a navigation or click, in ms")
    d.add_argument("--timeout", type=int, default=20000, help="navigation timeout in ms")
    d.add_argument("--full-page", action="store_true", default=True)
    d.add_argument("--no-full-page", dest="full_page", action="store_false")
    d.add_argument("--save-html", action="store_true", help="also save the DOM (HTML) of every page")

    x = p.add_argument_group("Dangerous options (normally not used)")
    x.add_argument("--allow-mutations", action="store_true", help="do not block requests other than GET. Never use this on a customer environment")
    x.add_argument("--allow-post-pattern", action="append", default=[], help="allow POST only to URLs that match this regular expression (GraphQL reads and the like). Be careful: mutations can slip in")

    p.add_argument("--rules", default=str(HERE / "safety_rules.json"), help="safety rules JSON")
    return p.parse_args()


# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------
def load_rules(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def norm_url(url: str, keep_query: bool, id_collapse: bool) -> str:
    u = urlparse(url)
    path = u.path or "/"
    if id_collapse:
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=/|$)", "/{uuid}", path, flags=re.I)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunparse((u.scheme, u.netloc.lower(), path, "", u.query if keep_query else "", ""))


def page_id(index: int) -> str:
    return f"p{index:03d}"


def text_key(*parts: str) -> str:
    return " ".join((x or "") for x in parts).lower()


def contains_any(hay: str, needles: list[str]) -> str | None:
    for n in needles:
        if n and n.lower() in hay:
            return n
    return None


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# Extracting information from a page (JS that runs in the browser)
# ----------------------------------------------------------------------------
EXTRACT_JS = r"""
(clickableSelector) => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const txt = (el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
  const attr = (el, a) => el.getAttribute(a) || '';
  const cssPath = (el) => {
    // Selectors that tend to stay stable: id > data-testid > path through the tree
    if (el.id) return '#' + CSS.escape(el.id);
    const tid = attr(el, 'data-testid'); if (tid) return `[data-testid="${tid}"]`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 8) {
      let sel = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      const sib = Array.from(cur.parentNode ? cur.parentNode.children : []).filter(c => c.tagName === cur.tagName);
      if (sib.length > 1) sel += `:nth-of-type(${sib.indexOf(cur) + 1})`;
      parts.unshift(sel);
      cur = cur.parentNode;
    }
    return parts.join(' > ');
  };

  const headings = Array.from(document.querySelectorAll('h1,h2,h3')).filter(vis).map(h => ({level: h.tagName, text: txt(h)})).slice(0, 60);

  const links = Array.from(document.querySelectorAll('a[href]')).filter(vis).map(a => ({
    text: txt(a), href: a.href, target: attr(a, 'target')
  })).slice(0, 500);

  const forms = Array.from(document.querySelectorAll('form, [role="form"]')).map((f, i) => ({
    index: i, action: attr(f, 'action'), method: (attr(f, 'method') || 'get').toUpperCase(), name: attr(f, 'name') || attr(f, 'id'),
    fields: Array.from(f.querySelectorAll('input,select,textarea')).map(el => ({
      tag: el.tagName.toLowerCase(), type: attr(el, 'type') || (el.tagName.toLowerCase()==='select'?'select':'text'),
      name: attr(el, 'name'), id: el.id, placeholder: attr(el, 'placeholder'), required: el.required || attr(el,'aria-required')==='true',
      label: (el.labels && el.labels[0]) ? txt(el.labels[0]) : (attr(el,'aria-label') || ''),
      options: el.tagName.toLowerCase()==='select' ? Array.from(el.options).map(o => txt(o)).slice(0, 30) : undefined,
      disabled: el.disabled, readonly: el.readOnly
    }))
  }));
  // Input elements outside any form
  const looseFields = Array.from(document.querySelectorAll('input,select,textarea')).filter(el => !el.closest('form') && vis(el)).map(el => ({
    tag: el.tagName.toLowerCase(), type: attr(el, 'type') || 'text', name: attr(el, 'name'), id: el.id, placeholder: attr(el, 'placeholder'),
    label: (el.labels && el.labels[0]) ? txt(el.labels[0]) : (attr(el,'aria-label') || '')
  }));

  const tables = Array.from(document.querySelectorAll('table')).filter(vis).map(t => ({
    caption: t.caption ? txt(t.caption) : '',
    headers: Array.from(t.querySelectorAll('thead th, tr:first-child th')).map(txt).slice(0, 40),
    rows: t.querySelectorAll('tbody tr').length
  })).slice(0, 30);

  const clickables = Array.from(document.querySelectorAll(clickableSelector)).filter(vis).map((el, i) => ({
    index: i, tag: el.tagName.toLowerCase(), text: txt(el), ariaLabel: attr(el, 'aria-label'), title: attr(el, 'title'),
    name: attr(el, 'name'), id: el.id, className: (typeof el.className === 'string' ? el.className : ''), type: attr(el, 'type'),
    role: attr(el, 'role'), href: attr(el, 'href'), value: attr(el, 'value'), disabled: !!el.disabled || attr(el,'aria-disabled')==='true',
    inForm: !!el.closest('form'), selector: cssPath(el)
  })).slice(0, 400);

  const nav = Array.from(document.querySelectorAll('nav, [role="navigation"], aside')).filter(vis).map(n => txt(n).slice(0, 400)).slice(0, 5);
  const bodyText = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 4000);
  const modals = Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"], .modal.show, .MuiDialog-root, dialog[open]')).filter(vis).map(m => ({ title: txt(m).slice(0, 200) }));

  return { title: document.title, headings, links, forms, looseFields, tables, clickables, nav, bodyText, modals,
           lang: document.documentElement.lang || '' };
}
"""


# ----------------------------------------------------------------------------
# Main part
# ----------------------------------------------------------------------------
class Crawler:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.rules = load_rules(args.rules)
        self.out = Path(args.out).resolve()
        self.shots = self.out / "screenshots"
        self.html_dir = self.out / "html"
        self.shots.mkdir(parents=True, exist_ok=True)
        if args.save_html:
            self.html_dir.mkdir(exist_ok=True)

        start = urlparse(args.url)
        self.origin = f"{start.scheme}://{start.netloc.lower()}"
        self.scope = [s.rstrip("/") for s in args.scope_prefix] or [self.origin]
        self.exclude = [re.compile(x, re.I) for x in args.exclude]
        self.allow_post = [re.compile(x, re.I) for x in args.allow_post_pattern]
        self.click_allow = re.compile(args.click_allow_pattern, re.I) if args.click_allow_pattern else None

        self.pages: dict[str, dict] = {}        # norm_url -> page record
        self.order: list[str] = []
        self.queue: deque[tuple[str, int, str | None]] = deque()
        self.blocked_requests: list[dict] = []
        self.skipped_elements: list[dict] = []
        self.skipped_urls: list[dict] = []
        self.errors: list[dict] = []
        self.log_path = self.out / "crawl.log"
        self._log_fh = open(self.log_path, "a", encoding="utf-8")

    # -- Log ---------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"[{now_iso()}] {msg}"
        print(line, flush=True)
        self._log_fh.write(line + "\n")
        self._log_fh.flush()

    # -- Safety checks -------------------------------------------------------------
    def url_in_scope(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        u = urlparse(url)
        if f"{u.scheme}://{u.netloc.lower()}" != self.origin:
            return False
        if not any(url.startswith(s) for s in self.scope):
            return False
        return not any(x.search(url) for x in self.exclude)

    def url_is_dangerous(self, url: str) -> str | None:
        return contains_any(url.lower(), self.rules.get("deny_url_keywords", []))

    def element_click_verdict(self, el: dict) -> tuple[bool, str]:
        """Returns (may it be clicked, reason)."""
        if el.get("disabled"):
            return False, "disabled"
        if (el.get("type") or "").lower() in {"submit", "reset", "image"}:
            return False, "submit/reset element"
        if el.get("tag") in {"input"}:
            return False, "input element"
        hay = text_key(el.get("text"), el.get("ariaLabel"), el.get("title"), el.get("name"), el.get("id"),
                       el.get("className"), el.get("value"), el.get("href"))
        hit = contains_any(hay, self.rules.get("deny_click_keywords", []))
        if hit:
            return False, f"Blocked keyword: {hit}"
        if el.get("inForm") and el.get("tag") == "button" and not (el.get("type") or "").lower() == "button":
            # a button inside a form with no type attribute acts as submit
            return False, "button without a type inside a form (= submit)"
        if self.click_allow and not self.click_allow.search(hay):
            return False, "does not match click-allow-pattern"
        label = (el.get("text") or el.get("ariaLabel") or el.get("title") or "").strip()
        if not label and not el.get("id") and not el.get("ariaLabel"):
            # an icon button without a label: there is no way to tell what it does, so it is not clicked by default
            return False, "No label (purpose unclear)"
        return True, "ok"

    # -- Blocking network requests -----------------------------------------------------
    def install_request_guard(self, context) -> None:
        def handler(route, request):
            m = request.method.upper()
            if m in SAFE_METHODS or self.args.allow_mutations:
                return route.continue_()
            if m == "POST" and any(p.search(request.url) for p in self.allow_post):
                return route.continue_()
            self.blocked_requests.append({"time": now_iso(), "method": m, "url": request.url, "page": self.current_url})
            self.log(f"BLOCKED {m} {request.url}")
            return route.abort("blockedbyclient")
        context.route("**/*", handler)

    def install_dialog_guard(self, page) -> None:
        def on_dialog(dialog):
            self.log(f"DIALOG dismissed ({dialog.type}): {dialog.message[:120]}")
            try:
                dialog.dismiss()
            except Exception:
                pass
        page.on("dialog", on_dialog)

    # -- Launching the browser ---------------------------------------------------------
    def launch(self, pw):
        a = self.args
        w, h = (int(x) for x in a.viewport.lower().split("x"))
        if a.cdp:
            browser = pw.chromium.connect_over_cdp(a.cdp)
            context = browser.contexts[0] if browser.contexts else browser.new_context(viewport={"width": w, "height": h})
            self.log(f"CDP connection: {a.cdp} (contexts={len(browser.contexts)})")
            return browser, context, True
        if a.profile:
            launch_args = ["--disable-blink-features=AutomationControlled"]
            if a.profile_directory:
                launch_args.append(f"--profile-directory={a.profile_directory}")
            context = pw.chromium.launch_persistent_context(
                a.profile, channel=a.channel or "chrome", headless=a.headless,
                viewport={"width": w, "height": h}, args=launch_args, accept_downloads=False,
            )
            self.log(f"Launched with profile: {a.profile} / {a.profile_directory or 'Default'} headless={a.headless}")
            return None, context, False
        browser = pw.chromium.launch(channel=a.channel, headless=a.headless)
        context = browser.new_context(viewport={"width": w, "height": h}, storage_state=a.storage_state, accept_downloads=False)
        self.log(f"Launched a new context storage_state={a.storage_state} headless={a.headless}")
        return browser, context, False

    # -- Crawl -----------------------------------------------------------------
    def run(self) -> None:
        self.current_url = self.args.url
        with sync_playwright() as pw:
            browser, context, attached = self.launch(pw)
            context.set_default_navigation_timeout(self.args.timeout)
            context.set_default_timeout(min(self.args.timeout, 8000))
            self.install_request_guard(context)
            page = context.new_page()
            self.install_dialog_guard(page)
            page.set_viewport_size({"width": int(self.args.viewport.split("x")[0]), "height": int(self.args.viewport.split("x")[1])})

            start_norm = norm_url(self.args.url, self.args.keep_query, self.args.id_collapse)
            self.queue.append((self.args.url, 0, None))
            seen = {start_norm}
            try:
                while self.queue and len(self.pages) < self.args.max_pages:
                    url, depth, parent = self.queue.popleft()
                    try:
                        self.visit(page, url, depth, parent, seen)
                    except Exception as e:  # keep going page by page
                        self.errors.append({"url": url, "error": repr(e), "trace": traceback.format_exc()[-1500:]})
                        self.log(f"ERROR {url}: {e!r}")
                    self.write_outputs()  # save the partial result as we go
            finally:
                self.write_outputs(final=True)
                try:
                    if attached:
                        page.close()  # never close the user's own browser
                    else:
                        context.close()
                        if browser:
                            browser.close()
                except Exception:
                    pass

    def goto(self, page, url: str) -> None:
        self.current_url = url
        try:
            page.goto(url, wait_until="domcontentloaded")
        except PWTimeout:
            self.log(f"goto timeout (domcontentloaded) {url}")
        try:
            page.wait_for_load_state("networkidle", timeout=min(self.args.timeout, 10000))
        except PWTimeout:
            pass
        page.wait_for_timeout(self.args.wait)

    def extract(self, page) -> dict:
        return page.evaluate(EXTRACT_JS, self.rules.get("clickable_selector"))

    def visit(self, page, url: str, depth: int, parent: str | None, seen: set[str]) -> None:
        nurl = norm_url(url, self.args.keep_query, self.args.id_collapse)
        pid = page_id(len(self.pages) + 1)
        self.log(f"VISIT {pid} depth={depth} {url}")
        self.goto(page, url)
        final_url = page.url
        final_norm = norm_url(final_url, self.args.keep_query, self.args.id_collapse)
        if final_norm != nurl and final_norm in self.pages:
            self.log(f"  -> redirect to already-visited {final_url}; skip")
            return
        if not self.url_in_scope(final_url):
            self.log(f"  -> redirected out of scope {final_url}; skip")
            return

        info = self.extract(page)
        shot = f"{pid}.png"
        page.screenshot(path=str(self.shots / shot), full_page=self.args.full_page)
        if self.args.save_html:
            (self.html_dir / f"{pid}.html").write_text(page.content(), encoding="utf-8")

        rec = {
            "id": pid, "url": final_url, "norm_url": final_norm, "requested_url": url, "depth": depth, "parent": parent,
            "title": info.get("title"), "lang": info.get("lang"), "visited_at": now_iso(), "screenshot": f"screenshots/{shot}",
            "headings": info.get("headings", []), "forms": info.get("forms", []), "looseFields": info.get("looseFields", []),
            "tables": info.get("tables", []), "nav": info.get("nav", []), "modals_on_load": info.get("modals", []),
            "bodyText": info.get("bodyText", ""), "links": [], "clickables": [], "states": [],
        }
        self.pages[final_norm] = rec
        self.order.append(final_norm)

        # --- collect links → queue
        self.enqueue_links(info.get("links", []), final_url, depth, pid, seen, rec)

        # --- click exploration
        if self.args.click_mode == "safe":
            self.explore_clicks(page, rec, info, depth, seen)

    def enqueue_links(self, links: list[dict], base: str, depth: int, pid: str, seen: set[str], rec: dict) -> None:
        known = {(l.get("text"), l.get("href")) for l in rec["links"]}
        for ln in links:
            href = urljoin(base, ln.get("href") or "")
            if (ln.get("text"), href) in known:
                continue
            known.add((ln.get("text"), href))
            entry = {"text": ln.get("text"), "href": href, "internal": self.url_in_scope(href)}
            if entry["internal"]:
                danger = self.url_is_dangerous(href)
                if danger:
                    entry["skipped"] = f"Risky URL keyword: {danger}"
                    if not any(s["page"] == pid and s["href"] == href for s in self.skipped_urls):
                        self.skipped_urls.append({"page": pid, "href": href, "reason": entry["skipped"]})
                else:
                    n = norm_url(href, self.args.keep_query, self.args.id_collapse)
                    entry["norm"] = n
                    if n not in seen and depth < self.args.max_depth:
                        seen.add(n)
                        self.queue.append((href, depth + 1, pid))
            rec["links"].append(entry)

    def explore_clicks(self, page, rec: dict, info: dict, depth: int, seen: set[str]) -> None:
        candidates = []
        for el in info.get("clickables", []):
            ok, reason = self.element_click_verdict(el)
            entry = {k: el.get(k) for k in ("index", "tag", "text", "ariaLabel", "title", "role", "type", "selector", "inForm", "disabled")}
            entry["clickable"] = ok
            entry["reason"] = reason
            rec["clickables"].append(entry)
            if ok:
                candidates.append(el)
            else:
                self.skipped_elements.append({"page": rec["id"], "text": el.get("text"), "selector": el.get("selector"), "reason": reason})
        candidates = candidates[: self.args.max_clicks_per_page]
        self.log(f"  clickables: {len(info.get('clickables', []))} total, {len(candidates)} safe")

        before_sig = dom_signature(info)
        page_url = rec["url"]
        for i, el in enumerate(candidates, start=1):
            sid = f"c{i:02d}"
            label = (el.get("text") or el.get("ariaLabel") or el.get("title") or el.get("id") or "")[:80]
            state = {"id": sid, "label": label, "selector": el.get("selector"), "role": el.get("role") or el.get("tag"), "result": None}
            try:
                # reload the page every time and make exactly one click from the initial state (no leftover state, deterministic result)
                self.goto(page, page_url)
                loc = page.locator(el["selector"]).first
                if loc.count() == 0 or not loc.is_visible():
                    state["result"] = "Element not found or hidden"
                    rec["states"].append(state)
                    continue
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=4000, no_wait_after=True)
                page.wait_for_timeout(self.args.wait)
                after_url = page.url
                after = self.extract(page)
                shot = f"{rec['id']}_{sid}.png"
                page.screenshot(path=str(self.shots / shot), full_page=self.args.full_page)
                state["screenshot"] = f"screenshots/{shot}"
                state["url_after"] = after_url
                state["modals"] = after.get("modals", [])
                state["headings_after"] = after.get("headings", [])[:10]
                # a change is detected from the DOM content (body text, headings, modals); comparing images would differ on a focus ring alone
                state["changed"] = dom_signature(after) != before_sig
                if norm_url(after_url, self.args.keep_query, self.args.id_collapse) != rec["norm_url"]:
                    state["result"] = "Page navigation"
                    if self.url_in_scope(after_url) and not self.url_is_dangerous(after_url):
                        n = norm_url(after_url, self.args.keep_query, self.args.id_collapse)
                        if n not in seen:
                            seen.add(n)
                            self.queue.append((after_url, depth + 1, rec["id"]))
                elif state["modals"]:
                    state["result"] = "Modal/dialog shown"
                    self.enqueue_links(after.get("links", []), after_url, depth, rec["id"], seen, rec)
                elif state["changed"]:
                    state["result"] = "In-page change (expanded section, tab, menu and so on)"
                    self.enqueue_links(after.get("links", []), after_url, depth, rec["id"], seen, rec)
                else:
                    state["result"] = "No change"
            except Exception as e:
                state["result"] = f"Error: {e!r}"[:200]
                self.log(f"  click error {label!r}: {e!r}")
            rec["states"].append(state)
            self.log(f"  {sid} {label!r} -> {state['result']}")

    def close_overlays(self, page) -> None:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        for sel in self.rules.get("close_selectors", []):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=1500, no_wait_after=True)
                    page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    # -- Output -----------------------------------------------------------------
    def write_outputs(self, final: bool = False) -> None:
        data = {
            "meta": {
                "start_url": self.args.url, "origin": self.origin, "scope": self.scope, "generated_at": now_iso(),
                "headless": self.args.headless, "click_mode": self.args.click_mode, "allow_mutations": self.args.allow_mutations,
                "page_count": len(self.pages), "state_count": sum(len(p["states"]) for p in self.pages.values()),
                "blocked_request_count": len(self.blocked_requests), "skipped_element_count": len(self.skipped_elements),
                "skipped_url_count": len(self.skipped_urls), "error_count": len(self.errors), "complete": final,
                "args": vars(self.args),
            },
            "pages": [self.pages[k] for k in self.order],
        }
        (self.out / "pages.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.out / "safety_report.json").write_text(json.dumps({
            "blocked_requests": self.blocked_requests, "skipped_elements": self.skipped_elements,
            "skipped_urls": self.skipped_urls, "errors": self.errors,
        }, ensure_ascii=False, indent=2), encoding="utf-8")


def dom_signature(info: dict) -> str:
    key = json.dumps({"t": info.get("bodyText"), "h": info.get("headings"), "m": info.get("modals"), "c": len(info.get("clickables", []))}, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def file_hash(p: Path) -> str:
    try:
        return hashlib.md5(p.read_bytes()).hexdigest()
    except FileNotFoundError:
        return ""


def main() -> None:
    args = parse_args()
    if not (args.profile or args.cdp or args.storage_state):
        print("Warning: none of --profile / --cdp / --storage-state was given. The crawl runs without a login.", file=sys.stderr)
    if args.allow_mutations:
        print("!!! --allow-mutations is set. Requests that change data are NOT blocked. Never use this on a customer environment !!!", file=sys.stderr)
        time.sleep(3)
    c = Crawler(args)
    c.log(f"start url={args.url} out={c.out}")
    c.run()
    c.log(f"done pages={len(c.pages)} blocked={len(c.blocked_requests)} skipped_elements={len(c.skipped_elements)} errors={len(c.errors)}")
    print(f"\nOutput: {c.out}/pages.json, {c.out}/screenshots/, {c.out}/safety_report.json")


if __name__ == "__main__":
    main()
