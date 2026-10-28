# browser-use の中で実行する、画面仕様書の見た目の確認（app_spec_crawler.py verify から呼ばれる。直接は使わない）。
# 代表のページを 幅 1440/390 で撮り、横のはみ出し・読めない画像・ライト固定（OS をダークにしても背景が明るいまま）を確かめる。
# 最後に 1 行 "ASC_VERIFY=<json>" を出す。
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
        # 中身の多いもの（ファイルが大きいもの）を代表にする
        files.sort(key=lambda f: -os.path.getsize(os.path.join(BOOK, sub, f)))
        targets.append((name, f"{sub}/{files[0]}"))

new_tab("about:blank")
tab = current_tab()["target_id"]
problems, shots = [], []
try:
    # OS がダークのときでもライトのままかを見るため、ダークを真似た状態で撮る
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
                problems.append(f"{rel}（幅 {w}px）: 横に {sw - w}px はみ出している")
            if broken and not mobile:
                problems.append(f"{rel}: 読み込めない画像 {len(broken)} 枚（例: {broken[0]}）")
            if not mobile and sum(bg) / 3 < 200:
                problems.append(f"{rel}: OS がダークのとき背景が暗くなる（rgb{tuple(bg)}）。ライト固定にする")
            path = os.path.join(SHOTS, f"{name}_{w}.png")
            capture_screenshot(path)
            shots.append(path)
finally:
    cdp("Emulation.clearDeviceMetricsOverride")
    cdp("Emulation.setEmulatedMedia", features=[])
    close_tab(tab)
print("ASC_VERIFY=" + json.dumps({"problems": problems, "shots": shots, "pages": [r for _, r in targets]}, ensure_ascii=False))
