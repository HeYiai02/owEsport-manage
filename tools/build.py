"""把全部素材生成 / 压缩 / 内联进 owcs-manager.html —— 产物永远只有一个 HTML 文件。

用法:
    python tools/build.py                 # 用缓存 + 必要时联网抓英雄头像
    python tools/build.py --procedural    # 英雄头像改成代码绘制的徽记(零外部素材)
    python tools/build.py --size 72       # 选手头像边长(默认 72)

素材来源与产物:
    assets/heroes.json        OverFast 英雄表(英雄名 → 官方立绘地址)
    assets/heroes/*.webp      英雄头像缓存(88×88)
    assets/players_raw/*.jpg  选手原图缓存(由 fetch_players.py 抓)
    assets/players/*.webp     选手头像缓存(72×72,构建时从原图裁)
    assets/maps.json          OverFast 地图表(地图名 → 官方截图地址)
    assets/maps_raw/*.jpg     地图原图缓存
    assets/maps/*.webp        地图背景缓存(800×320 横条)

    → 写回 owcs-manager.html 里的 HERO_IMG / PLAYER_IMG / MAP_IMG 三个 base64 区块
"""
import base64
import io
import json
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
HTML = os.path.join(ROOT, "owcs-manager.html")
API = "https://overfast-api.tekrop.fr/heroes"
API_MAPS = "https://overfast-api.tekrop.fr/maps"
UA = {"User-Agent": "Mozilla/5.0 (local fan project)"}

HERO_SIZE = 88
HERO_Q = 78
PLAYER_SIZE = 72
PLAYER_Q = 74
MAP_SIZE = (720, 288)
MAP_Q = 58

ROLE_COLOR = {
    "tank": ((58, 108, 190), (150, 190, 255)),
    "dps": ((176, 66, 56), (255, 158, 132)),
    "sup": ((40, 138, 96), (128, 226, 172)),
}


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def read_html():
    return open(HTML, encoding="utf-8").read()


def write_html(src):
    open(HTML, "w", encoding="utf-8").write(src)


def safe(name):
    out = name
    for ch in ':/\\*?"<>|':
        out = out.replace(ch, "_")
    return out.strip()


# ---------------------------------------------------------------- 英雄

def hero_names(src):
    block = src[src.index("const HEROES = ["):src.index("].map(h=>({name:h[0]")]
    return re.findall(r'\["([^"]+)","(?:tank|dps|sup)"', block)


def hero_meta(src):
    """从 HEROES 数组里拿到 name→(role, arch)。"""
    block = src[src.index("const HEROES = ["):src.index("].map(h=>({name:h[0]")]
    return {n: (r, a) for n, r, a in re.findall(r'\["([^"]+)","(tank|dps|sup)","([a-z]+)"\]', block)}


def load_hero_list():
    cache = os.path.join(ASSETS, "heroes.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    data = json.loads(fetch(API).decode("utf-8"))
    os.makedirs(ASSETS, exist_ok=True)
    json.dump(data, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return data


def head_crop(im):
    w, h = im.size
    if abs(w - h) <= 2:
        return im
    side = min(w, h)
    top = 0 if h >= w else (h - w) // 2
    left = (w - side) // 2
    return im.crop((left, max(0, top), left + side, max(0, top) + side))


def hero_bytes(url):
    im = Image.open(io.BytesIO(fetch(url))).convert("RGBA")
    im = head_crop(im).resize((HERO_SIZE, HERO_SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=HERO_Q, method=6, alpha_quality=90)
    return buf.getvalue()


def font(size):
    for name in ("arialbd.ttf", "seguisb.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def initials(name):
    """Soldier: 76 → S76,D.Va → DV,Wrecking Ball → WB。"""
    flat = re.sub(r"[^A-Za-z0-9]", "", name)
    if re.search(r"\d", flat):
        letters = re.sub(r"[^A-Za-z]", "", flat)[:1]
        digits = re.sub(r"[^0-9]", "", flat)
        return (letters + digits).upper()
    parts = [p for p in re.split(r"[\s.\-]+", name) if p and re.search(r"[A-Za-z]", p)]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (flat[:2] or "?").upper()


def emblem(name, role, arch):
    """完全由代码绘制的英雄徽记:渐变底 + 首字母 + 体系小图标。"""
    S = HERO_SIZE
    c0, c1 = ROLE_COLOR.get(role, ((90, 90, 110), (170, 170, 200)))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=(
            int(c0[0] + (c1[0] - c0[0]) * t),
            int(c0[1] + (c1[1] - c0[1]) * t),
            int(c0[2] + (c1[2] - c0[2]) * t), 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # 上半部分压暗一点,让字更清楚
    shade = Image.new("RGBA", (S, S), (0, 0, 0, 60))
    img.alpha_composite(Image.composite(shade, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    txt = initials(name)
    f = font(int(S * 0.40) if len(txt) <= 2 else int(S * 0.30))
    box = d.textbbox((0, 0), txt, font=f)
    d.text(((S - (box[2] - box[0])) / 2 - box[0], (S - (box[3] - box[1])) / 2 - box[1] - S * 0.04),
           txt, font=f, fill=(255, 255, 255, 235))

    # 体系图标:突进=尖三角 / 近身=方块 / 远程=同心圆
    a = int(S * 0.24)
    x0, y0 = S - a - int(S * 0.10), S - a - int(S * 0.10)
    col = (255, 255, 255, 160)
    if arch == "dive":
        d.polygon([(x0 + a / 2, y0), (x0 + a, y0 + a), (x0, y0 + a)], fill=col)
    elif arch == "brawl":
        d.rectangle([x0, y0, x0 + a, y0 + a], fill=col)
    else:
        d.ellipse([x0, y0, x0 + a, y0 + a], outline=col, width=max(2, a // 6))

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=90, method=6, alpha_quality=100)
    return buf.getvalue()


def build_heroes(src, procedural=False):
    names = hero_names(src)
    meta = hero_meta(src)
    os.makedirs(os.path.join(ASSETS, "heroes"), exist_ok=True)
    by_name = {}
    if not procedural:
        by_name = {h["name"]: h for h in load_hero_list()}
        lack = [n for n in names if n not in by_name]
        if lack:
            print("!! 英雄表里找不到:", lack)
            return None

    out, total = {}, 0
    for i, name in enumerate(names, 1):
        path = os.path.join(ASSETS, "heroes", safe(name) + ".webp")
        if procedural:
            data = emblem(name, meta.get(name, ("dps", "poke"))[0], meta.get(name, ("dps", "poke"))[1])
        elif os.path.exists(path):
            data = open(path, "rb").read()
        else:
            data = hero_bytes(by_name[name]["portrait"])
            open(path, "wb").write(data)
        total += len(data)
        out[name] = "data:image/webp;base64," + base64.b64encode(data).decode()
        print(f"\r  英雄 {i}/{len(names)} {name:<18} {len(data) // 1024}KB", end="")
    mode = "代码绘制" if procedural else "官方立绘"
    print(f"\n  英雄 {len(out)} 个({mode}),webp 合计 {total / 1024:.0f}KB")
    return out


# ---------------------------------------------------------------- 选手

def player_names(src):
    block = src[src.index("const BASE_PLAYERS = ["):src.index("let P_CARDS")]
    seen, out = set(), []
    for n in re.findall(r'P\("([^"]+)"', block):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def player_crop(im, size=PLAYER_SIZE):
    """选手照大多是现场半身/全身照:取顶部 72% 高度的正方形,把头和肩框进去。
    实测比整图等比缩放的辨识度高得多。"""
    im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.size
    side = min(w, int(h * 0.72))
    left = (w - side) // 2
    return im.crop((left, 0, left + side, side)).resize((size, size), Image.LANCZOS)


def build_players(src):
    names = player_names(src)
    raw_dir = os.path.join(ASSETS, "players_raw")
    out_dir = os.path.join(ASSETS, "players")
    os.makedirs(out_dir, exist_ok=True)
    out, total, miss = {}, 0, []
    for i, name in enumerate(names, 1):
        src_path = os.path.join(raw_dir, safe(name) + ".jpg")
        path = os.path.join(out_dir, safe(name) + ".webp")
        if os.path.exists(path):
            data = open(path, "rb").read()
        elif os.path.exists(src_path):
            im = player_crop(Image.open(src_path))
            buf = io.BytesIO()
            im.save(buf, format="WEBP", quality=PLAYER_Q, method=6)
            data = buf.getvalue()
            open(path, "wb").write(data)
        else:
            miss.append(name)
            continue
        total += len(data)
        out[name] = "data:image/webp;base64," + base64.b64encode(data).decode()
        print(f"\r  选手 {i}/{len(names)} {name:<12} {len(data) // 1024}KB", end="")
    print(f"\n  选手 {len(out)}/{len(names)} 有照片,webp 合计 {total / 1024:.0f}KB")
    if miss:
        print("  没照片(用首字母头像顶上):", ", ".join(miss))
    return out


# ---------------------------------------------------------------- 地图

def map_names(src):
    block = src[src.index("const MAPS = ["):src.index("].map(m=>({name:m[0]")]
    return re.findall(r'\["([^"]+)","(?:Control|Escort|Hybrid|Push|Flashpoint|Clash)"\]', block)


def norm_name(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("\u2019", "'").lower()
    return "".join(c for c in s if c.isalnum())


def load_map_list():
    cache = os.path.join(ASSETS, "maps.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    data = json.loads(fetch(API_MAPS).decode("utf-8"))
    os.makedirs(ASSETS, exist_ok=True)
    json.dump(data, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return data


def find_map(name, table):
    """官方表里的名字可能少了 "Watchpoint: " 前缀,或者用弯引号。"""
    n = norm_name(name)
    if n in table:
        return table[n]
    for pre in ("watchpoint", "map", "the"):
        if n.startswith(pre) and n[len(pre):] in table:
            return table[n[len(pre):]]
    return None


def encode_map(raw):
    """把官方地图截图压成 2.5:1 的横条背景(上下裁,保留地平线),再压暗一点点。"""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    want = MAP_SIZE[0] / MAP_SIZE[1]
    ch = int(w / want)
    if ch <= h:
        top = int((h - ch) * 0.42)
        im = im.crop((0, top, w, top + ch))
    else:
        cw = int(h * want)
        left = (w - cw) // 2
        im = im.crop((left, 0, left + cw, h))
    im = im.resize(MAP_SIZE, Image.LANCZOS)
    im = ImageEnhance.Brightness(im).enhance(0.9)
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=MAP_Q, method=6)
    return buf.getvalue()


def build_maps(src):
    names = map_names(src)
    raw_dir = os.path.join(ASSETS, "maps_raw")
    out_dir = os.path.join(ASSETS, "maps")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    table = {norm_name(d["name"]): d for d in load_map_list()}
    out, total, miss = {}, 0, []
    for i, name in enumerate(names, 1):
        path = os.path.join(out_dir, safe(name) + ".webp")
        raw_path = os.path.join(raw_dir, safe(name) + ".jpg")
        if os.path.exists(path):
            data = open(path, "rb").read()
        else:
            if os.path.exists(raw_path) and os.path.getsize(raw_path) < 2048:
                os.remove(raw_path)                 # 上次抓失败留下的空文件
            if not os.path.exists(raw_path):
                hit = find_map(name, table)
                if not hit:
                    miss.append(name)
                    continue
                try:
                    raw = fetch(hit["screenshot"])
                except Exception as e:              # 官方表里有条目但图还没传
                    print(f"\n  !! {name} 截图取不到({e}),先用渐变底")
                    miss.append(name)
                    continue
                open(raw_path, "wb").write(raw)
            data = encode_map(open(raw_path, "rb").read())
            open(path, "wb").write(data)
        total += len(data)
        out[name] = "data:image/webp;base64," + base64.b64encode(data).decode()
        print(f"\r  地图 {i}/{len(names)} {name:<24} {len(data) // 1024}KB", end="")
    print(f"\n  地图 {len(out)}/{len(names)} 有背景图,webp 合计 {total / 1024:.0f}KB")
    if miss:
        print("  没找到截图(用渐变底顶上):", ", ".join(miss))
    return out


# ---------------------------------------------------------------- 写回

def js_object(var, mapping):
    body = ",\n".join(f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v)}'
                      for k, v in mapping.items())
    return f"const {var} = {{\n{body}\n}};"


def inject(src, marker, js):
    pat = rf"/\* {marker}:BEGIN \*/.*?/\* {marker}:END \*/"
    new, n = re.subn(pat, f"/* {marker}:BEGIN */\n{js}\n/* {marker}:END */", src, flags=re.S)
    if n != 1:
        raise SystemExit(f"!! 找不到 {marker} 标记块({n})")
    return new


def main():
    args = sys.argv[1:]
    procedural = "--procedural" in args
    if "--size" in args:
        global PLAYER_SIZE
        PLAYER_SIZE = int(args[args.index("--size") + 1])

    src = read_html()
    heroes = build_heroes(src, procedural)
    if heroes is None:
        return 1
    players = build_players(src)
    maps = build_maps(src)

    src = inject(src, "ASSETS", js_object("HERO_IMG", heroes))
    src = inject(src, "PLAYER_ASSETS", js_object("PLAYER_IMG", players))
    src = inject(src, "MAP_ASSETS", js_object("MAP_IMG", maps))
    write_html(src)
    print(f"已写入 {HTML} — {len(src.encode('utf-8')) / 1024:.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
