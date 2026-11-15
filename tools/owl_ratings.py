# -*- coding: utf-8 -*-
"""把 OWL 逐图数据折算成卡牌四维 + 招牌英雄,写入 data/owl/ratings.json。

口径(全部来自 OWL Stats Lab 官方 phs_*.zip):
  1. 统计先换成 per-10-min 速率;
  2. 在 (位置, 赛季) 组内 z-score(不足 5 人退回同位置全体),不同年份节奏不同不能混池;
  3. 枪法 = z(Elim)·.35 + z(FinalBlow)·.30 + z(HeroDmg)·.20 + z(SoloKill)·.15
     意识 = -z(Deaths)·.55 + z(大招效率 = 使用/获得)·.25 + z(Assist)·.20
     心态 = 逐图影响力的稳定度(1 - 变异系数)在同位置里的百分位
     英雄池 = 出战 ≥60 分钟的不同英雄数 N,按 POOL_BY_COUNT 取分(和游戏内公式一致)
  4. mech/iq/mental 各做一次仿射校准(中位数 82、标准差 4.0),不改变相对次序;
  5. 样本 <300 分钟的卡向同位置均值收缩,标 low=True。
"""
import io, os, sys, json, re, statistics as st, unicodedata
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = r"E:\code\wishingWell\data\owl"
HTML = r"E:\code\wishingWell\owcs-manager.html"
OUT = os.path.join(D, "ratings.json")

POOL_BY_COUNT = {1: 58, 2: 68, 3: 76, 4: 84, 5: 90}
W_ROLE = {"tank": (.30, .35, .15, .20), "dps": (.45, .20, .20, .15), "sup": (.20, .35, .25, .20)}
MIN_MIN, HERO_MIN = 300.0, 60.0
HERO_ALIAS = {"mccree": "cassidy"}


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def overall_of(role, mech, iq, pool, mental):
    a, b, c, d = W_ROLE[role]
    return round(a * mech + b * iq + c * pool + d * mental)


def per10(x, tp):
    return x * 600.0 / tp if tp > 0 else 0.0


def zmap(vals):
    if len(vals) < 2:
        return {k: 0.0 for k, _ in vals}
    m = st.mean(v for _, v in vals)
    sd = st.pstdev(v for _, v in vals)
    return {k: ((v - m) / sd if sd > 1e-9 else 0.0) for k, v in vals}


def pct_rank(vals):
    if len(vals) < 2:
        return {k: .5 for k, _ in vals}
    xs = sorted(v for _, v in vals)
    return {k: (sum(1 for x in xs if x < v) + .5 * sum(1 for x in xs if x == v)) / len(xs)
            for k, v in vals}


def affine(scores, mean=82.0, sd=4.0, lo=68, hi=95):
    xs = list(scores.values())
    m, s0 = st.mean(xs), (st.pstdev(xs) or 1.0)
    return {k: max(lo, min(hi, round(mean + (v - m) / s0 * sd))) for k, v in scores.items()}


def parse_cards(src):
    i0 = src.index("const BASE_PLAYERS = [")
    i1 = src.index("let P_CARDS")
    out = []
    for m in re.finditer(r'P\("([^"]+)",(\d{4}),"(tank|dps|sup)"', src[i0:i1]):
        out.append((m.group(1), int(m.group(2)), m.group(3)))
    return out


def main():
    src = io.open(HTML, encoding="utf-8").read()
    cards = parse_cards(src)

    hi = src.index("const HEROES = [")
    hero_names = re.findall(r'\["([^"]+)",\s*"(?:tank|dps|sup)"', src[hi:src.index("];", hi)])
    HNAME = {fold(n): n for n in hero_names}

    data = json.load(io.open(os.path.join(D, "extract.json"), encoding="utf-8"))
    role_of = {(fold(n), y): r for n, y, r in cards}
    key_of = {}
    for n, y, r in cards:
        key_of[(fold(n), y)] = n

    recs = []
    for season, players in data.items():
        yr = int(season)
        for key, d in players.items():
            tp = d.get("tp", 0)
            if tp < 600:
                continue
            role = role_of.get((key, yr))
            if not role:
                continue
            recs.append(dict(season=yr, key=key, name=key_of.get((key, yr), key), role=role, tp=tp,
                             e10=per10(d.get("elim", 0), tp), f10=per10(d.get("fb", 0), tp),
                             d10=per10(d.get("deaths", 0), tp), hd10=per10(d.get("hd", 0), tp),
                             solo10=per10(d.get("solo", 0), tp), asst10=per10(d.get("asst", 0), tp),
                             ult_eff=(d.get("ult_used", 0) / d["ult_earned"]) if d.get("ult_earned") else .5,
                             maps=d.get("maps", []), heroes=d.get("heroes", {})))

    z = {}
    for met in ("e10", "f10", "hd10", "solo10", "d10", "asst10", "ult_eff"):
        out, small, big = {}, defaultdict(list), defaultdict(list)
        for r in recs:
            big[(r["role"], r["season"])].append((id(r), r[met]))
        for (role, season), lst in big.items():
            (out.update(zmap(lst)) if len(lst) >= 5 else small[role].extend(lst))
        for role, lst in small.items():
            out.update(zmap(lst))
        z[met] = out

    for r in recs:
        imps = []
        for mp in r["maps"]:
            tp = mp.get("tp", 0)
            if tp < 120:
                continue
            imps.append(per10(mp.get("fb", 0) * 1.5 + mp.get("elim", 0) * .6
                              + mp.get("hd", 0) / 1000. - mp.get("deaths", 0) * 1.1, tp))
        r["cons"] = (1.0 - min(1.0, st.pstdev(imps) / st.mean(imps))) if len(imps) >= 3 and st.mean(imps) > .2 else None

    cons_rank, by = {}, defaultdict(list)
    for r in recs:
        if r["cons"] is not None:
            by[r["role"]].append((id(r), r["cons"]))
    for role, lst in by.items():
        cons_rank.update(pct_rank(lst))

    raw_m, raw_i, raw_n = {}, {}, {}
    for r in recs:
        i = id(r)
        raw_m[i] = z["e10"][i] * .35 + z["f10"][i] * .30 + z["hd10"][i] * .20 + z["solo10"][i] * .15
        raw_i[i] = -z["d10"][i] * .55 + z["ult_eff"][i] * .25 + z["asst10"][i] * .20
        raw_n[i] = (cons_rank.get(i, .5) - .5) * 2

    mech, iq, men = affine(raw_m), affine(raw_i), affine(raw_n, sd=3.2)

    role_ok = defaultdict(list)
    for r in recs:
        if r["tp"] >= MIN_MIN * 60:
            role_ok[r["role"]].append(mech[id(r)])
    role_mean = {k: st.mean(v) for k, v in role_ok.items()}

    out = {}
    for r in recs:
        i, mins = id(r), r["tp"] / 60.0
        w = 1.0 if mins >= MIN_MIN else max(.35, mins / MIN_MIN)
        mm = round(w * mech[i] + (1 - w) * role_mean.get(r["role"], 82))
        qq = round(w * iq[i] + (1 - w) * 82)
        mt = men[i]
        # 招牌英雄:打满 HERO_MIN 分钟的,按时间排序,最多 5 个
        hl = []
        for h, t in sorted(r["heroes"].items(), key=lambda kv: -kv[1]):
            name = HNAME.get(HERO_ALIAS.get(fold(h), fold(h)))
            if name and t >= HERO_MIN * 60 and name not in hl:
                hl.append(name)
            if len(hl) >= 5:
                break
        if not hl:
            for h, t in sorted(r["heroes"].items(), key=lambda kv: -kv[1]):
                name = HNAME.get(HERO_ALIAS.get(fold(h), fold(h)))
                if name and name not in hl:
                    hl.append(name)
                if len(hl) >= 2:
                    break
        pool = POOL_BY_COUNT.get(len(hl), 90)
        out["%s|%d" % (fold(r["name"]), r["season"])] = dict(
            name=r["name"], mech=mm, iq=qq, pool=pool, mental=mt,
            overall=overall_of(r["role"], mm, qq, pool, mt),
            heroes=hl, minutes=round(mins), maps=len(r["maps"]),
            low=mins < MIN_MIN,
            src="OWL %d · %d 分钟 / %d 张图" % (r["season"], round(mins), len(r["maps"])))

    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=0))

    print("%-14s %-4s %-5s | %-6s -> %-16s | heroes" % ("name", "yr", "role", "old", "new"))
    for n, y, role in sorted(cards, key=lambda x: (x[1], x[0])):
        k = "%s|%d" % (fold(n), y)
        if k not in out:
            continue
        r = out[k]
        print("%-14s %-4d %-5s | %-6s -> %2d/%2d/%2d/%2d=%2d | %s%s"
              % (n, y, role, "", r["mech"], r["iq"], r["pool"], r["mental"], r["overall"],
                 ", ".join(r["heroes"]), "  <300min" if r["low"] else ""))
    ovs = [v["overall"] for v in out.values()]
    print("matched %d/%d | overall %d-%d median %d" % (len(out), len(cards), min(ovs), max(ovs), st.median(ovs)))


if __name__ == "__main__":
    main()
