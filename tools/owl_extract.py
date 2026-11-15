# -*- coding: utf-8 -*-
"""从 OWL Stats Lab 的 phs_*.zip 里抽出我们卡池里选手的逐图数据。

产物:E:\code\wishingWell\data\owl\extract.json
  { "season": { "player": { sums..., "maps":[{...}], "heroes":{hero:seconds} } } }

只读一遍 CSV,后面调评分公式不用再扫 600MB。
"""
import io, os, sys, csv, json, zipfile, re, time
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = r"E:\code\wishingWell\data\owl"
OUT = os.path.join(D, "extract.json")

FILES = {
    2018: ("phs_2018.zip", ["phs_2018_stage_1.csv", "phs_2018_stage_2.csv", "phs_2018_stage_3.csv",
                            "phs_2018_stage_4.csv", "phs_2018_playoffs.csv"]),
    2019: ("phs_2019.zip", ["phs_2019_stage_1.csv", "phs_2019_stage_2.csv", "phs_2019_stage_3.csv",
                            "phs_2019_stage_4.csv", "phs_2019_playoffs.csv"]),
    2020: ("phs_2020.zip", ["phs_2020_1.csv", "phs_2020_2.csv"]),
    2021: ("phs_2021.zip", ["phs_2021_1.csv"]),
    2022: ("phs_2022.zip", ["phs-2022.csv"]),
    2023: ("phs_2023.zip", ["phs-2023-000000000000 (2).csv"]),
}

# 只关心这些统计项(其余扔掉,省内存)
WANT = {
    "Time Played": "tp",
    "Eliminations": "elim",
    "Final Blows": "fb",
    "Deaths": "deaths",
    "Hero Damage Done": "hd",
    "Healing Done": "heal",
    "Ultimates Used": "ult_used",
    "Ultimates Earned - Fractional": "ult_earned",
    "Damage Taken": "dt",
    "Solo Kills": "solo",
    "Objective Kills": "objk",
    "Assists": "asst",
    "Time Alive": "alive",
    "Shots Fired": "shots",
    "Shots Hit": "shots_hit",
    "Critical Hits": "crit",
}

ALIAS = {"sp9rk1e": "sparkle"}


def norm(s):
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return ALIAS.get(s, s)


def col(head, *names):
    for n in names:
        if n in head:
            return head.index(n)
    return None


def main():
    # 我们的卡池
    src = io.open(r"E:\code\wishingWell\owcs-manager.html", encoding="utf-8").read()
    body = src[src.index("const BASE_PLAYERS = ["):src.index("let P_CARDS")]
    cards = [(m.group(1), int(m.group(2))) for m in re.finditer(r'P\("([^"]+)",(\d{4}),', body)]
    want = defaultdict(set)
    for n, y in cards:
        want[y].add(norm(n))

    out = {}
    for season, (zipname, members) in FILES.items():
        t0 = time.time()
        per = {}          # player -> dict
        maps = defaultdict(lambda: defaultdict(float))   # (player, mid, map) -> sums
        heroes = defaultdict(lambda: defaultdict(float))  # player -> hero -> seconds
        with zipfile.ZipFile(os.path.join(D, zipname)) as z:
            for m in members:
                with z.open(m) as f:
                    r = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"))
                    head = next(r)
                    ip = col(head, "player_name", "player")
                    ist = col(head, "stat_name", "stat")
                    ih = col(head, "hero_name", "hero")
                    iv = col(head, "stat_amount", "amount")
                    im = col(head, "esports_match_id", "match_id")
                    imap = col(head, "map_name")
                    for row in r:
                        if len(row) <= max(ip, ist, ih, iv, im, imap):
                            continue
                        name = norm(row[ip])
                        if name not in want[season]:
                            continue
                        stat = row[ist]
                        hero = row[ih]
                        try:
                            val = float(row[iv])
                        except ValueError:
                            continue
                        if hero == "All Heroes":
                            key = WANT.get(stat)
                            if not key:
                                continue
                            d = per.setdefault(name, defaultdict(float))
                            d[key] += val
                            maps[(name, row[im], row[imap])][key] += val
                        elif stat == "Time Played":
                            heroes[name][hero] += val

        for name, d in per.items():
            d = dict(d)
            d["maps"] = [dict(v) for k, v in maps.items() if k[0] == name]
            d["heroes"] = dict(heroes.get(name, {}))
            out.setdefault(str(season), {})[name] = d
        print(season, "players", len(per), "%.1fs" % (time.time() - t0))

    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False))
    print("wrote", OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    main()
