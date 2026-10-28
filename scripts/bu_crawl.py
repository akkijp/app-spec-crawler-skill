# browser-use の中で実行する巡回スクリプト（app_spec_crawler.py crawl から呼ばれる。直接は使わない）。
# helpers（goto_url / js / cdp / capture_screenshot など）は browser-use が読み込み済み。
# 画面は URL で開くだけ。入力・送信はしない。クリックするのは「#xxx」へのページ内タブだけ（--no-tabs で止められる）。
# 最後に 1 行 "ASC_STATUS=<more|done|session|start_failed|error> <説明>" を出す。
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
ROUTE = C.get("route_param") or ""
VARIANTS = C.get("variant_params") or []
SCOPE = C["scope_prefix"]
HIDE = ",".join(C["hide_selectors"])
SESSION_RE = re.compile("|".join(C["session_error_patterns"]), re.I) if C.get("session_error_patterns") else None


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def finish(status, msg=""):
    if status != "more":  # 続きが無い・止まったときは作業用のタブを閉じる（続きは新しいタブで回す）
        try:
            close_tab(st.get("tab"))
        except Exception:
            pass
    print(f"ASC_STATUS={status} {msg}".strip())
    raise SystemExit(0)


st = json.load(open(SP)) if os.path.exists(SP) else {
    "base": C["url"].split("?")[0], "queue": [[C["url"], None, 0]], "seen": [], "pages": [],
    "skipped_urls": [], "skipped_elements": [], "errors": [], "log": [], "tab": None}
# ログインし直して URL のトークンが変わったときは、積んである URL の頭を新しいものに置き換える
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
    """画面を見分けるパスと、残すクエリ。route_param があればその値をパスとして扱う"""
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
    if not url.startswith(SCOPE):
        return "スコープ外"
    for pat in C.get("exclude", []):
        if re.search(pat, url):
            return f"除外パターン: {pat}"
    path, _ = route_of(url)
    if path in C.get("allow_routes", []):
        return None
    u = urlparse(url)
    target = (path + "?" + ("" if ROUTE else u.query)).lower()
    for k in DENY_URL:
        if k and k in target:
            return f"危険URLキーワード: {k}"
    return None


EXTRACT = r"""(() => {
  const t = s => (s||'').replace(/\s+/g,' ').trim();
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const lab = el => { if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return t(l.innerText).slice(0,60); }
    const p = el.closest('label'); if (p) return t(p.innerText).slice(0,60);
    const tr = el.closest('tr'); if (tr) { const th = tr.querySelector('th'); if (th) return t(th.innerText).slice(0,60); }
    const td = el.closest('td'); if (td && td.previousElementSibling) return t(td.previousElementSibling.innerText).slice(0,60);
    return el.getAttribute('aria-label') || ''; };
  const field = el => ({tag: el.tagName.toLowerCase(), type: el.type||'', name: el.name||'', id: el.id||'', placeholder: el.placeholder||'',
    required: !!el.required, label: lab(el), options: el.tagName==='SELECT' ? [...el.options].slice(0,30).map(o=>t(o.text)) : undefined});
  const onclickHref = b => { const m=(b.getAttribute('onclick')||'').match(/location\.href\s*=\s*['"]([^'"]+)['"]/); return m ? new URL(m[1].replace(/&amp;/g,'&'), location.href).href : null; };
  return {
    title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis).map(h=>({level:h.tagName, text:t(h.innerText).slice(0,120)})).filter(h=>h.text).slice(0,80),
    forms: [...document.forms].map((f,i)=>({index:i, action:(f.getAttribute('action')||'').slice(0,200), method:(f.method||'get').toUpperCase(), name:f.name||f.id||'',
      fields:[...f.elements].filter(e=>['INPUT','SELECT','TEXTAREA'].includes(e.tagName) && e.type!=='hidden' && vis(e)).slice(0,120).map(field)})).filter(f=>f.fields.length),
    tables: [...document.querySelectorAll('table')].filter(vis).slice(0,30).map(tb=>({caption:t(tb.caption&&tb.caption.innerText),
      headers:[...tb.querySelectorAll('thead th, tr:first-child th')].map(th=>t(th.innerText).slice(0,40)).slice(0,60), rows: tb.querySelectorAll('tbody tr').length})),
    nav: [...document.querySelectorAll('nav, [role=navigation]')].filter(vis).map(n=>t(n.innerText).slice(0,600)).slice(0,5),
    bodyText: t(document.body.innerText).slice(0,4000),
    links: [...document.querySelectorAll('a[href]')].map(a=>({text:t(a.innerText||a.title||a.getAttribute('aria-label')).slice(0,60), href:a.href}))
      .concat([...document.querySelectorAll('[onclick*="location.href"]')].map(b=>({text:t(b.innerText||b.value||b.title).slice(0,60), href:onclickHref(b), via:'onclick'})).filter(l=>l.href)),
    buttons: [...document.querySelectorAll('button, input[type=button], input[type=submit], input[type=reset], [role=button], [role=tab], a[href^="#"], a[href^="javascript"]')].filter(vis).slice(0,150)
      .map(b=>({tag:b.tagName.toLowerCase(), text:t(b.innerText||b.value||b.title||b.getAttribute('aria-label')).slice(0,60), type:b.type||'', role:b.getAttribute('role')||'', id:b.id||'', inForm: !!b.closest('form')})),
    // ページ内タブ = 今のページと同じ URL で、# の後ろに名前があるリンク（onclick 付きは除く）
    tabs: [...document.querySelectorAll('a[href*="#"]')].filter(a=>vis(a) && !a.getAttribute('onclick')
      && a.href.split('#')[0]===location.href.split('#')[0] && /^[A-Za-z][\w-]*$/.test(a.href.split('#')[1]||''))
      .map(a=>({text:t(a.innerText).slice(0,40), hash:'#'+a.href.split('#')[1]})).filter(x=>x.text).slice(0,12)
  };
})()"""


def hide_overlays():
    if HIDE:
        js("(()=>{const s=document.createElement('style');s.textContent=%s+'{display:none!important}';document.head.appendChild(s);})()" % json.dumps(HIDE))


def shot(path):
    hide_overlays()
    time.sleep(0.3)
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    h = js("Math.min(document.documentElement.scrollHeight, 6000)") or 900
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=int(h), deviceScaleFactor=1, mobile=False)
    time.sleep(0.3)
    capture_screenshot(path)
    cdp("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)


def session_lost(url_now):
    m = SESSION_RE.search(js("document.body ? document.body.innerText.slice(0,3000) : ''") or "") if SESSION_RE else None
    if m:
        return f"画面に「{m.group(0)}」と出た（ログインが切れたときの表示）"
    if not url_now.startswith(SCOPE):
        return f"スコープの外（{url_now[:80]}）に飛ばされた。ログイン画面への転送と思われる"
    return None


def write_outputs(complete):
    pages = st["pages"]
    meta = {"start_url": C["url_display"], "origin": f'{urlparse(C["url"]).scheme}://{urlparse(C["url"]).netloc}', "scope": [C["scope_display"]],
            "generated_at": now(), "headless": False, "click_mode": "tabs" if C.get("tabs", True) else "none", "allow_mutations": False,
            "page_count": len(pages), "state_count": sum(len(p["states"]) for p in pages), "blocked_request_count": 0,
            "skipped_element_count": len(st["skipped_elements"]), "skipped_url_count": len(st["skipped_urls"]), "error_count": len(st["errors"]),
            "complete": complete, "method": "browser-use（URL で開く巡回・ページ内タブのみクリック）"}
    json.dump({"meta": meta, "pages": pages}, open(os.path.join(OUT, "pages.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"blocked_requests": [], "skipped_elements": st["skipped_elements"], "skipped_urls": st["skipped_urls"], "errors": st["errors"]},
              open(os.path.join(OUT, "safety_report.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(OUT, "crawl.log"), "w").write("\n".join(st["log"]) + "\n")


def save():
    st["seen"] = sorted(seen)
    json.dump(st, open(SP, "w"), ensure_ascii=False)


# 作業用のタブ（前回の続きなら同じタブ）
tabs = {t["target_id"]: t for t in list_tabs()}
if st.get("tab") and st["tab"] in tabs:
    switch_tab(st["tab"])
else:
    new_tab("about:blank")
    st["tab"] = current_tab()["target_id"]
title_fix = re.compile(r"^\S*🐴\s*")

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
        time.sleep(C["wait"])
        lost = session_lost(page_info()["url"])
        if lost:
            st["queue"].insert(0, [url, parent, depth])
            seen.discard(k)
            save()
            write_outputs(False)
            if not st["pages"]:
                finish("start_failed", lost)
            finish("session", lost)
        d = js(EXTRACT)
        shot(os.path.join(OUT, "screenshots", f"{pid}.png"))
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
            reason = f"禁止キーワード: {hit}" if hit else ("ラベル無し" if not txt else "未クリック（URL で開く方式）")
            clickables.append({"index": i, **b, "clickable": False, "reason": reason})
            if hit:
                st["skipped_elements"].append({"page": pid, "text": b["text"], "selector": b["id"], "reason": reason})
        states = []
        if C.get("tabs", True):
            for t in list({t["hash"]: t for t in d["tabs"]}.values()):
                if any(w and w in t["text"].lower() for w in DENY_CLICK):
                    continue
                sid = f"c{len(states) + 1:02d}"
                goto_url(url)
                wait_for_load()
                time.sleep(C["wait"])
                ok = js("(()=>{const a=[...document.querySelectorAll('a[href]')].find(a=>a.offsetWidth && !a.getAttribute('onclick') && (a.getAttribute('href')||'').endsWith(%s)); if(!a) return false; a.click(); return true;})()" % json.dumps(t["hash"]))
                if not ok:
                    continue
                time.sleep(0.8)
                shot(os.path.join(OUT, "screenshots", f"{pid}_{sid}.png"))
                states.append({"id": sid, "label": f"タブ「{t['text']}」", "selector": f"a[href$='{t['hash']}']", "role": "tab", "result": "画面内変化",
                               "screenshot": f"screenshots/{pid}_{sid}.png", "url_after": url.split("#")[0] + t["hash"], "modals": [], "changed": True})
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
        finish("done", f"上限 {C['max_pages']} 画面に達した（未訪問 {len(st['queue'])} 件）")
    finish("done", f"{len(st['pages'])} 画面")
finish("more", f"{len(st['pages'])} 画面済み・未訪問 {len(st['queue'])} 件")
