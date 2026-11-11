# The visual check of the screen spec. It runs inside browser-use (called by "app_spec_crawler.py verify"; not used directly).
# It takes screenshots of representative pages at widths 1440 and 390, and checks for horizontal overflow, images that
# fail to load, and the fixed light theme (the background must stay light even when the OS is in dark mode).
# At the end it prints one line: "ASC_VERIFY=<json>".
import json
import os
import time

C = json.load(open(os.environ["ASC_CONFIG"]))
BOOK, SHOTS = C["book"], C["shots"]
os.makedirs(SHOTS, exist_ok=True)
base = "file://" + BOOK.rstrip("/") + "/"
targets = [("index", "index.html"), ("overview", "overview.html")]
if os.path.exists(os.path.join(BOOK, "guide.html")):
    targets.insert(1, ("guide", "guide.html"))
for sub, name in (("sections", "section"), ("pages", "page"), ("captures", "capture")):
    files = sorted(f for f in os.listdir(os.path.join(BOOK, sub)) if f.endswith(".html")) if os.path.isdir(os.path.join(BOOK, sub)) else []
    if files:
        # Use the page with the most content (the largest file) as the representative
        files.sort(key=lambda f: -os.path.getsize(os.path.join(BOOK, sub, f)))
        targets.append((name, f"{sub}/{files[0]}"))

new_tab("about:blank")
tab = current_tab()["target_id"]
problems, shots = [], []
try:
    # Emulate dark mode while taking the screenshots, to see that the pages stay light when the OS is dark
    cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
    for w, h, mobile in ((1440, 900, False), (390, 844, True)):
        cdp("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mobile)
        for name, rel in targets:
            goto_url(base + rel)
            wait_for_load()
            time.sleep(0.4)
            sw = js("document.documentElement.scrollWidth")
            broken = js("[...document.querySelectorAll('img')].filter(i=>i.complete && i.naturalWidth===0).map(i=>i.getAttribute('src'))") or []
            bg = js("(getComputedStyle(document.body).backgroundColor.match(/\\d+/g)||[255,255,255]).slice(0,3).map(Number)")
            if sw > w + 1:
                problems.append(f"{rel} (width {w}px): overflows horizontally by {sw - w}px")
            if broken and not mobile:
                problems.append(f"{rel}: {len(broken)} image(s) failed to load (example: {broken[0]})")
            if not mobile and sum(bg) / 3 < 200:
                problems.append(f"{rel}: the background turns dark when the OS is in dark mode (rgb{tuple(bg)}). Keep the light theme fixed")
            path = os.path.join(SHOTS, f"{name}_{w}.png")
            capture_screenshot(path)
            shots.append(path)
finally:
    cdp("Emulation.clearDeviceMetricsOverride")
    cdp("Emulation.setEmulatedMedia", features=[])
    close_tab(tab)
print("ASC_VERIFY=" + json.dumps({"problems": problems, "shots": shots, "pages": [r for _, r in targets]}, ensure_ascii=False))
