# The crawl script that runs inside browser-use (called by `app_spec_crawler.py crawl`; not meant to be run directly).
# The helpers (goto_url / js / cdp / capture_screenshot ...) are already loaded by browser-use.
# Screens are only ever opened by URL. Nothing is typed and nothing is submitted. The only clicks are on in-page tabs
# (links to "#name" on the current page), and --no-tabs turns even those off.
# The last line printed is "ASC_STATUS=<more|done|session|start_failed|error> <message>".
# The fixed phrases written into pages.json (state labels, results, reasons) are English; build_book.py translates them.
import hashlib
import datetime as dt
import json
import os
import re
import time
import traceback
from urllib.parse import parse_qs, urlparse

C = json.load(open(os.environ["ASC_CONFIG"]))
OUT = C["out"]
SP = os.path.join(OUT, "state.json")
os.makedirs(os.path.join(OUT, "screenshots"), exist_ok=True)
RULES = json.load(open(C["rules"]))
DENY_URL = [k.lower() for k in RULES["deny_url_keywords"] + C.get("extra_deny", [])]
DENY_CLICK = [k.lower() for k in RULES["deny_click_keywords"]]
TOKEN_PARAMS = {k.lower() for k in RULES.get("state_token_params", [])}
ACTION_PARAMS = {k.lower() for k in RULES.get("action_params", [])}
SAFE_ACTIONS = {k.lower() for k in RULES.get("safe_action_values", [])}
ROUTE = C.get("route_param") or ""
VARIANTS = C.get("variant_params") or []
SCOPE = C["scope_prefix"]
HIDE = ",".join(C["hide_selectors"])
LOGIN_PATH_RE = re.compile(r"/(log_?in|sign_?in|signin|auth/login)(/|$)", re.I)  # what a login screen's URL path looks like
SESSION_RE = re.compile("|".join(C["session_error_patterns"]), re.I) if C.get("session_error_patterns") else None


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def finish(status, msg=""):
    if status != "more":  # finished or stopped: close the working tab (a resumed run opens a new one)
        try:
            close_tab(st.get("tab"))
        except Exception:
            pass
    print(f"ASC_STATUS={status} {msg}".strip())
    raise SystemExit(0)


st = json.load(open(SP)) if os.path.exists(SP) else {
    "base": C["url"].split("?")[0], "queue": [[C["url"], None, 0]], "seen": [], "pages": [],
    "skipped_urls": [], "skipped_elements": [], "errors": [], "log": [], "tab": None}
# After a re-login the token in the URL may have changed: rewrite the head of every queued URL to the new one
new_base = C["url"].split("?")[0]
if st.get("base") and st["base"] != new_base:
    st["queue"] = [[u.replace(st["base"], new_base, 1), p, d] for u, p, d in st["queue"]]
    st["base"] = new_base
seen = set(st["seen"])


def log(m):
    st["log"].append(f"{now()} {m}")
    print(m)


ID_SEG = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{24,})$", re.I)


def route_of(url):
    """The path that identifies a screen, and the query parts to keep. With route_param, that parameter's value is the path."""
    u = urlparse(url)
    q = parse_qs(u.query)
    if ROUTE:
        path = (q.get(ROUTE) or ["/"])[0] or "/"
    else:
        path = u.path or "/"
        if C.get("id_collapse", True):
            path = "/".join("{id}" if ID_SEG.match(s) else s for s in path.split("/"))
    keep = [f"{k}={q[k][0]}" for k in VARIANTS if k in q]
    if C.get("keep_query") and not ROUTE:
        keep = [f"{k}={v[0]}" for k, v in sorted(q.items())]
    return path, keep


def key_of(url):
    path, keep = route_of(url)
    return path + ("?" + "&".join(keep) if keep else "")


def norm_of(url):
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}{key_of(url)}"


def verdict(url):
    """Why this URL must not be opened, or None if it may be."""
    if not url.startswith(SCOPE):
        return "Out of scope"
    for pat in C.get("exclude", []):
        if re.search(pat, url):
            return f"Excluded pattern: {pat}"
    u = urlparse(url)
    q = parse_qs(u.query, keep_blank_values=True)
    # Some apps change data on a plain GET link ("Trash", "Activate", "Approve"). Two signs give such links away:
    # an anti-forgery token in the query, and an action parameter whose value is not a known read-only one.
    # These two rules apply even to --allow-route screens.
    if not C.get("allow_token_urls"):
        for name in q:
            if name.lower() in TOKEN_PARAMS:
                return f"State-changing token in URL: {name}"
    for name, vals in q.items():
        if name.lower() in ACTION_PARAMS and name != ROUTE:
            val = (vals[0] if vals else "").lower()
            if val not in SAFE_ACTIONS:
                return f"State-changing action: {name}={val[:40]}"
    path, _ = route_of(url)
    if path in C.get("allow_routes", []):
        return None
    target = (path + "?" + ("" if ROUTE else u.query)).lower()
    for k in DENY_URL:
        if k and k in target:
            return f"Risky URL keyword: {k}"
    return None


EXTRACT = r"""(() => {
  const t = s => (s||'').replace(/\s+/g,' ').trim();
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const lab = el => { if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return t(l.innerText).slice(0,60); }
    const p = el.closest('label'); if (p) return t(p.innerText).slice(0,60);
    const tr = el.closest('tr'); if (tr) { const th = tr.querySelector('th'); if (th) return t(th.innerText).slice(0,60); }
    const td = el.closest('td'); if (td && td.previousElementSibling) return t(td.previousElementSibling.innerText).slice(0,60);
    return el.getAttribute('aria-label') || ''; };
  const field = el => ({tag: el.tagName.toLowerCase(), type: String(el.getAttribute('type')||el.type||''), name: el.getAttribute('name')||'', id: el.getAttribute('id')||'', placeholder: el.getAttribute('placeholder')||'',
    required: !!el.required, label: lab(el), options: el.tagName==='SELECT' ? [...el.options].slice(0,30).map(o=>t(o.text)) : undefined});
  const onclickHref = b => { const m=(b.getAttribute('onclick')||'').match(/location\.href\s*=\s*['"]([^'"]+)['"]/); return m ? new URL(m[1].replace(/&amp;/g,'&'), location.href).href : null; };
  return {
    title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis).map(h=>({level:h.tagName, text:t(h.innerText).slice(0,120)})).filter(h=>h.text).slice(0,80),
    forms: [...document.forms].map((f,i)=>({index:i, action:(f.getAttribute('action')||'').slice(0,200), method:(f.getAttribute('method')||'get').toUpperCase(), name:f.getAttribute('name')||f.getAttribute('id')||'',
      fields:[...f.elements].filter(e=>['INPUT','SELECT','TEXTAREA'].includes(e.tagName) && e.type!=='hidden' && vis(e)).slice(0,120).map(field)})).filter(f=>f.fields.length),
    tables: [...document.querySelectorAll('table')].filter(vis).slice(0,30).map(tb=>({caption:t(tb.caption&&tb.caption.innerText),
      headers:[...tb.querySelectorAll('thead th, tr:first-child th')].map(th=>t(th.innerText).slice(0,40)).slice(0,60), rows: tb.querySelectorAll('tbody tr').length})),
    nav: [...document.querySelectorAll('nav, [role=navigation]')].filter(vis).map(n=>t(n.innerText).slice(0,600)).slice(0,5),
    bodyText: t(document.body.innerText).slice(0,40000),
    links: [...document.querySelectorAll('a[href]')].map(a=>({text:t(a.innerText||a.title||a.getAttribute('aria-label')).slice(0,60), href:a.href}))
      .concat([...document.querySelectorAll('[onclick*="location.href"]')].map(b=>({text:t(b.innerText||b.value||b.title).slice(0,60), href:onclickHref(b), via:'onclick'})).filter(l=>l.href)),
    buttons: [...document.querySelectorAll('button, input[type=button], input[type=submit], input[type=reset], [role=button], [role=tab], a[href^="#"], a[href^="javascript"]')].filter(vis).slice(0,150)
      .map(b=>({tag:b.tagName.toLowerCase(), text:t(b.innerText||b.value||b.title||b.getAttribute('aria-label')).slice(0,60), type:b.type||'', role:b.getAttribute('role')||'', id:b.id||'', inForm: !!b.closest('form')})),
    // In-page tab = a link to the current URL with a name after '#' (links with onclick are excluded).
    // Skip links for screen readers ("Skip to main content") are not tabs.
    tabs: [...document.querySelectorAll('a[href*="#"]')].filter(a=>vis(a) && !a.getAttribute('onclick')
      && !/skip|screen-reader|sr-only|visually-hidden/i.test(a.className||'') && !/^(skip to|jump to|本文へ|メインコンテンツへ)/i.test(t(a.innerText))
      && a.href.split('#')[0]===location.href.split('#')[0] && /^[A-Za-z][\w-]*$/.test(a.href.split('#')[1]||''))
      .map(a=>({text:t(a.innerText).slice(0,40), hash:'#'+a.href.split('#')[1]})).filter(x=>x.text).slice(0,12)
  };
})()"""


SETTLE = r"""(() => {
  const b = document.body; if (!b) return 'none';
  const txt = (b.innerText || '');
  const busy = document.querySelectorAll('[aria-busy="true"]').length
    + (/(still loading|loading\s*(…|\.\.\.)|読み込み中|加载中|로딩 중|cargando\s*(…|\.\.\.))/i.test(txt.slice(0, 20000)) ? 1 : 0);
  const imgs = [...document.images].filter(i => !i.complete).length;
  return [document.readyState, document.getElementsByTagName('*').length, txt.length, imgs, busy].join('|');
})()"""


def settle():
    """Wait until the page has finished drawing: at least C["wait"] seconds, then until two consecutive looks at the page
    are identical and nothing says "loading", but never longer than C["settle_max"] seconds. Returns the seconds waited."""
    t0 = time.time()
    time.sleep(C["wait"])
    limit = max(float(C.get("settle_max", 8.0)), C["wait"])
    prev, same = None, 0
    while time.time() - t0 < limit:
        sig = js(SETTLE) or ""
        idle = sig.startswith("complete") and sig.endswith("|0|0")
        same = same + 1 if (sig == prev and idle) else 0
        if same >= 2:
            break
        prev = sig
        time.sleep(0.4)
    return round(time.time() - t0, 1)


def fingerprint(d):
    """What a screen shows, reduced to a hash. Two URLs with the same fingerprint are the same screen under two addresses."""
    body = re.sub(r"\s+", " ", d.get("bodyText") or "")[:8000]
    heads = "|".join(h["text"] for h in d.get("headings", []))
    fields = sum(len(f["fields"]) for f in d.get("forms", []))
    return hashlib.sha1(f'{d.get("title")}\n{heads}\n{fields}\n{body}'.encode("utf-8")).hexdigest()


def hide_overlays():
    if HIDE:
        js("(()=>{const s=document.createElement('style');s.textContent=%s+'{display:none!important}';document.head.appendChild(s);})()" % json.dumps(HIDE))


EXPAND = r"""(() => {
  // Expand scrollable boxes inside the page (content taller than the box) to their full height. This changes only how the DOM is drawn; nothing is sent to the server.
  let n = 0;
  for (const e of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(e);
    if (/(auto|scroll)/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 50 && e.clientHeight > 150) {
      for (const [k, v] of [['height', 'auto'], ['max-height', 'none'], ['overflow', 'visible']]) e.style.setProperty(k, v, 'important');
      n++;
    }
  }
  if (n) for (const e of [document.documentElement, document.body])
    for (const [k, v] of [['height', 'auto'], ['max-height', 'none'], ['overflow', 'visible']]) e.style.setProperty(k, v, 'important');
  return n;
})()"""

TILE = 6000        # height of one image; a taller screen continues in further images (pXXX_s02.png ...)
MAX_TILES = 20     # limit per screen (120000px); what is left out is noted in the log


def shot(path):
    """Capture the whole page. A screen taller than TILE is captured in parts; returns [(relative image path, top, bottom), ...] without the first part."""
    hide_overlays()
    time.sleep(0.3)
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    js(EXPAND)
    time.sleep(0.3)
    full = js("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)") or 900
    full = int(full)
    tiles = []
    y = 0
    while y < full and len(tiles) < MAX_TILES:
        hgt = min(TILE, full - y)
        cdp("Emulation.setDeviceMetricsOverride", width=1400, height=max(int(hgt), 300), deviceScaleFactor=1, mobile=False)
        js(f"window.scrollTo(0, {y})")
        time.sleep(0.4)
        out = path if y == 0 else path[:-4] + f"_s{len(tiles) + 1:02d}.png"
        capture_screenshot(out)
        tiles.append((os.path.relpath(out, OUT), y, y + hgt))
        y += hgt
    js("window.scrollTo(0, 0)")
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    if y < full:
        log(f"NOTE {os.path.basename(path)}: captured {y}px of {full}px (limit {MAX_TILES} images)")
    return tiles[1:]


def tile_states(tiles, start):
    return [{"id": f"s{i + 2:02d}", "label": f"Part {i + 2}/{len(tiles) + 1} ({a}–{b}px)", "selector": "", "role": "scroll", "result": "Continuation of a tall screen",
             "screenshot": rel, "url_after": "", "modals": [], "changed": False} for i, (rel, a, b) in enumerate(tiles)][start:]


def session_lost(url_now):
    m = SESSION_RE.search(js("document.body ? document.body.innerText.slice(0,3000) : ''") or "") if SESSION_RE else None
    if m:
        return f"the page shows \"{m.group(0)}\" (what it displays when the login has expired)"
    if not url_now.startswith(SCOPE):
        return f"redirected out of scope ({url_now[:80]}); probably a redirect to the login screen"
    # Sent back to a login screen on the same domain (e.g. /login/client/?url=..., /users/sign_in).
    # It is inside the scope, so the check above misses it and the crawl would keep capturing the login screen as content.
    if LOGIN_PATH_RE.search(urlparse(url_now).path) and js("!!document.querySelector('input[type=password]')"):
        return f"sent back to the login screen ({url_now[:80]}); the login has probably expired"
    return None


def write_outputs(complete):
    pages = st["pages"]
    meta = {"start_url": C["url_display"], "origin": f'{urlparse(C["url"]).scheme}://{urlparse(C["url"]).netloc}', "scope": [C["scope_display"]],
            "generated_at": now(), "headless": False, "click_mode": "tabs" if C.get("tabs", True) else "none", "allow_mutations": False,
            "page_count": len(pages), "state_count": sum(len(p["states"]) for p in pages), "blocked_request_count": 0,
            "skipped_element_count": len(st["skipped_elements"]), "skipped_url_count": len(st["skipped_urls"]), "error_count": len(st["errors"]),
            "complete": complete, "method": "browser-use (opens pages by URL; clicks in-page tabs only)", "duplicate_count": len(st.get("duplicates", []))}
    json.dump({"meta": meta, "pages": pages}, open(os.path.join(OUT, "pages.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"blocked_requests": [], "skipped_elements": st["skipped_elements"], "skipped_urls": st["skipped_urls"], "errors": st["errors"],
               "duplicates": st.get("duplicates", [])},
              open(os.path.join(OUT, "safety_report.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(OUT, "crawl.log"), "w").write("\n".join(st["log"]) + "\n")


def save():
    st["seen"] = sorted(seen)
    json.dump(st, open(SP, "w"), ensure_ascii=False)


# The working tab (the same one when resuming)
tabs = {t["target_id"]: t for t in list_tabs()}
if st.get("tab") and st["tab"] in tabs:
    switch_tab(st["tab"])
else:
    new_tab("about:blank")
    st["tab"] = current_tab()["target_id"]
title_fix = re.compile(r"^\S*🐴\s*")

# --retry-errors: put the screens that failed last time back at the head of the queue (and forget that they were opened)
if C.get("retry_errors") and st["errors"] and st.get("retried_run") != C.get("run_id"):
    for e in reversed(st["errors"]):
        seen.discard(key_of(e["url"]))
        st["queue"].insert(0, [e["url"], None, 1])
    log(f"retrying {len(st['errors'])} screens that failed last time")
    st["errors"] = []
    st["retried_run"] = C.get("run_id")  # the crawl runs in batches of 30 screens, so retry only once per command

done = 0
while st["queue"] and done < C["batch"] and len(st["pages"]) < C["max_pages"]:
    url, parent, depth = st["queue"].pop(0)
    k = key_of(url)
    if k in seen or depth > C["max_depth"]:
        continue
    seen.add(k)
    pid = f"p{len(st['pages']) + 1:03d}"
    try:
        goto_url(url)
        wait_for_load()
        settle()
        lost = session_lost(page_info()["url"])
        if lost:
            st["queue"].insert(0, [url, parent, depth])
            seen.discard(k)
            save()
            write_outputs(False)
            if not st["pages"]:
                finish("start_failed", lost)
            finish("session", lost)
        # Receive it as a string: if an element slips in, CDP fails with "Object reference chain is too long" and hides the cause
        d = json.loads(js("JSON.stringify(" + EXTRACT + ")"))
        fp = fingerprint(d)
        twin = st.setdefault("fingerprints", {}).get(fp)
        if twin and C.get("dedupe", True):
            # The same screen under a second URL (e.g. /admin/ and /admin/index.php): record it and move on
            st.setdefault("duplicates", []).append({"url": url, "page_key": k, "duplicate_of": twin, "found_on": parent})
            st["skipped_urls"].append({"page": parent or "", "href": url, "reason": f"Duplicate of {twin}"})
            log(f"DUP {k} = {twin}")
            save()
            continue
        st["fingerprints"][fp] = pid
        tiles = shot(os.path.join(OUT, "screenshots", f"{pid}.png"))
        cur = page_info()["url"]
        links = []
        for l in d["links"]:
            h = l["href"].split("#")[0] if l.get("via") != "onclick" else l["href"]
            internal = h.startswith(SCOPE)
            ent = {"text": l["text"], "href": l["href"], "internal": internal}
            if internal:
                ent["norm"] = norm_of(h)
                v = verdict(h)
                if v:
                    ent["skipped"] = v
                    st["skipped_urls"].append({"page": pid, "href": h, "reason": v})
                elif key_of(h) not in seen:
                    st["queue"].append([h, pid, depth + 1])
            links.append(ent)
        clickables = []
        for i, b in enumerate(d["buttons"]):
            txt = (b["text"] or "").lower()
            hit = next((w for w in DENY_CLICK if w and w in txt), None)
            reason = f"Blocked keyword: {hit}" if hit else ("No label" if not txt else "Not clicked (pages are opened by URL)")
            clickables.append({"index": i, **b, "clickable": False, "reason": reason})
            if hit:
                st["skipped_elements"].append({"page": pid, "text": b["text"], "selector": b["id"], "reason": reason})
        states = tile_states(tiles, 0)
        if C.get("tabs", True):
            for t in list({t["hash"]: t for t in d["tabs"]}.values()):
                if any(w and w in t["text"].lower() for w in DENY_CLICK):
                    continue
                sid = f"c{len([x for x in states if x['id'].startswith('c')]) + 1:02d}"
                goto_url(url)
                wait_for_load()
                settle()
                ok = js("(()=>{const a=[...document.querySelectorAll('a[href]')].find(a=>a.offsetWidth && !a.getAttribute('onclick') && (a.getAttribute('href')||'').endsWith(%s)); if(!a) return false; a.click(); return true;})()" % json.dumps(t["hash"]))
                if not ok:
                    continue
                time.sleep(0.8)
                more = shot(os.path.join(OUT, "screenshots", f"{pid}_{sid}.png"))
                states.append({"id": sid, "label": f'Tab "{t["text"]}"', "selector": f"a[href$='{t['hash']}']", "role": "tab", "result": "In-page change",
                               "screenshot": f"screenshots/{pid}_{sid}.png", "url_after": url.split("#")[0] + t["hash"], "modals": [], "changed": True})
                for j, (rel, a, b) in enumerate(more):
                    states.append({"id": f"{sid}_s{j + 2:02d}", "label": f'Tab "{t["text"]}", continued ({a}–{b}px)', "selector": "", "role": "scroll",
                                   "result": "Continuation of a tall screen", "screenshot": rel, "url_after": "", "modals": [], "changed": False})
        st["pages"].append({"id": pid, "url": cur, "norm_url": norm_of(url), "requested_url": url, "depth": depth, "parent": parent,
                            "title": title_fix.sub("", d["title"] or ""), "visited_at": now(), "screenshot": f"screenshots/{pid}.png", "page_key": k,
                            "headings": d["headings"], "forms": d["forms"], "looseFields": [], "tables": d["tables"], "nav": d["nav"],
                            "modals_on_load": [], "bodyText": d["bodyText"], "links": links, "clickables": clickables, "states": states})
        log(f"{pid} {k} links={len(links)} tabs={len(states)}")
        done += 1
    except SystemExit:
        raise
    except Exception as e:
        st["errors"].append({"url": url, "error": repr(e)[:300], "time": now()})
        log(f"ERROR {k} {e!r}"[:300])
    save()

save()
complete = not st["queue"] or len(st["pages"]) >= C["max_pages"]
write_outputs(complete)
if complete:
    if len(st["pages"]) >= C["max_pages"] and st["queue"]:
        finish("done", f"reached the limit of {C['max_pages']} screens ({len(st['queue'])} not visited)")
    finish("done", f"{len(st['pages'])} screens")
finish("more", f"{len(st['pages'])} screens done, {len(st['queue'])} not visited")
