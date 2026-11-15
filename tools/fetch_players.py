"""抓取选手头像。

为什么走 Wayback Machine:直接打 Liquipedia 的 API 很快会被 429(还连累正常访问),
而 Wayback 里存着大量 Liquipedia 选手页的快照,连页面里的头像图一起存了。
用 archive.org 拿快照 → 从快照 HTML 里取 infobox 头像地址 → 从 archive.org 下原图。
全程不碰 liquipedia.net,不会触发它的限流。

用法:
    python tools/fetch_players.py [--force]

产物:
    assets/players_raw/<name>.jpg   原图缓存(已存在就跳过)
    assets/players_raw/_report.json 每个选手的结果
"""
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "owcs-manager.html")
RAW = os.path.join(ROOT, "assets", "players_raw")
UA = "OWCSManagerBot/0.2 (local fan project)"

DELAY = 1.0
RETRIES = 4
THUMB_W = 420


def get(url, timeout=60, delay=DELAY, tries=RETRIES):
    last = None
    for attempt in range(tries):
        if delay:
            time.sleep(delay * (1.6 ** attempt))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return r.status, raw
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503, 502, 504):
                continue
            raise
        except Exception as e:      # 超时/连接重置也重试
            last = e
            continue
    raise last


def player_names():
    src = open(HTML, encoding="utf-8").read()
    block = src[src.index("const BASE_PLAYERS = ["):src.index("let P_CARDS")]
    seen, out = set(), []
    for n in re.findall(r'P\("([^"]+)"', block):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def safe(name):
    out = name
    for ch in ':/\\*?"<>|':
        out = out.replace(ch, "_")
    return out.strip()


def snapshot(name):
    """返回 (timestamp, page_url) 或 (None, None)。"""
    q = "https://archive.org/wayback/available?url=" + urllib.parse.quote(
        "liquipedia.net/overwatch/" + name.replace(" ", "_"))
    _, raw = get(q)
    snap = json.loads(raw).get("archived_snapshots", {}).get("closest", {})
    if not snap.get("url"):
        return None, None
    return snap.get("timestamp"), snap["url"].replace("http://", "https://")


def infobox_img(page_url):
    _, raw = get(page_url)
    txt = raw.decode("utf-8", "replace")
    m = re.search(r'infobox-image-wrapper.*?<img[^>]+src="([^"]+)"', txt, re.S)
    return m.group(1) if m else None


def shrink(src, width=THUMB_W):
    """缩略图尺寸不要改:Wayback 只存了当年那个尺寸,换尺寸会 404。"""
    return src


def main():
    force = "--force" in sys.argv
    os.makedirs(RAW, exist_ok=True)
    names = player_names()
    todo = [n for n in names if force or not os.path.exists(os.path.join(RAW, safe(n) + ".jpg"))]
    print(f"选手 {len(names)} 位,需要抓 {len(todo)} 位")
    if not todo:
        print("全部已缓存")
        return 0

    report, missing = {}, []
    for i, name in enumerate(todo, 1):
        path = os.path.join(RAW, safe(name) + ".jpg")
        try:
            ts, url = snapshot(name)
            if not url:
                report[name] = "no-snapshot"
                missing.append(name)
                print(f"\r{i}/{len(todo)} {name:<12} NO SNAPSHOT", end="")
                continue
            src = infobox_img(url)
            if not src:
                report[name] = "no-image-in-page"
                missing.append(name)
                print(f"\r{i}/{len(todo)} {name:<12} NO IMAGE", end="")
                continue
            img_url = "https://web.archive.org" + shrink(src) if src.startswith("/web/") else src
            _, blob = get(img_url)
            if len(blob) < 1500:
                raise ValueError("too small")
            open(path, "wb").write(blob)
            report[name] = img_url
            print(f"\r{i}/{len(todo)} {name:<12} {len(blob)//1024}KB", end="")
        except Exception as e:
            report[name] = f"err {type(e).__name__}: {e}"
            missing.append(name)
            print(f"\r{i}/{len(todo)} {name:<12} ERR {type(e).__name__} {e}", end="")

    rp = os.path.join(RAW, "_report.json")
    old = {}
    if os.path.exists(rp):
        try:
            old = json.load(open(rp, encoding="utf-8"))
        except Exception:
            old = {}
    old.update(report)
    json.dump(old, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n完成:{len(todo) - len(missing)}/{len(todo)}")
    if missing:
        print("没抓到:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
