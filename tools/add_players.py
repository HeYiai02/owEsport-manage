# -*- coding: utf-8 -*-
"""把选手卡 / 战队追加进 owcs-manager.html。

用法:
    python tools/add_players.py tools/new_players.json
    python tools/add_players.py tools/new_teams.json --teams

JSON 格式(选手):
    [{"name":"Someone","season":2025,"role":"tank",
      "mech":90,"iq":85,"pool":72,"mental":84,
      "heroes":["Winston","D.Va","Hazard"],"note":"Team Falcons"}]

JSON 格式(战队,加 --teams):
    [{"name":"Twisted Minds","region":"EMEA",
      "players":["Void@2021","Leave@2021",null,"ChiYo@2025","Fielder@2022"]}]

会被校验的东西:位置只能是 tank/dps/sup;英雄必须在 HEROES 里登记;
同名同赛季的卡不会重复插入。
"""
import io
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HTML = r"E:\code\wishingWell\owcs-manager.html"
for a in sys.argv[1:]:
    if a.startswith("--html="):
        HTML = a.split("=", 1)[1]
ROLES = ("tank", "dps", "sup")


def load(src):
    return io.open(src, encoding="utf-8").read()


def hero_names(html):
    block = html[html.index("const HEROES"):]
    block = block[:block.index("\n];")]
    return set(re.findall(r'\["([^"]+)",', block))


def existing_cards(html):
    block = html[html.index("const BASE_PLAYERS"):]
    block = block[:block.index("\n];")]
    return set((n, int(y)) for n, y in re.findall(r'P\("([^"]+)",\s*(\d+)', block))


def fmt_card(rec):
    heroes = ",".join('"%s"' % h for h in rec["heroes"])
    return ('  P("%s",%d,"%s",%d,%d,%d,%d,[%s],"%s"),\n'
            % (rec["name"], rec["season"], rec["role"],
               rec["mech"], rec["iq"], rec["pool"], rec["mental"],
               heroes, rec.get("note", "")))


def add_cards(html, records):
    known = hero_names(html)
    have = existing_cards(html)
    out, skipped, bad = [], [], []
    for r in records:
        key = (r["name"], int(r["season"]))
        if key in have:
            skipped.append("%s@%s(已存在)" % key)
            continue
        if r["role"] not in ROLES:
            bad.append("%s: 位置 %s 不合法" % (r["name"], r["role"]))
            continue
        miss = [h for h in r["heroes"] if h not in known]
        if not r["heroes"]:
            bad.append("%s: 没有英雄" % r["name"])
            continue
        if miss:
            bad.append("%s: 英雄没登记 %s" % (r["name"], "、".join(miss)))
            continue
        have.add(key)
        out.append(fmt_card(r))

    if not out:
        return html, skipped, bad

    i = html.index("const BASE_PLAYERS")
    j = html.index("\n];", i)
    head = html[:j]
    if not head.rstrip().endswith(","):
        head = head.rstrip() + ","
    return head + "\n" + "".join(out).rstrip("\n") + html[j:], skipped, bad


def add_teams(html, teams):
    block = html[html.index("const OPP_TEAMS"):]
    block = block[:block.index("\n];")]
    have = set(re.findall(r'name:"([^"]+)"', block))
    lines, skipped, bad = [], [], []
    for t in teams:
        if t["name"] in have:
            skipped.append(t["name"] + "(已存在)")
            continue
        if len(t["players"]) != 5:
            bad.append("%s: 只有 %d 个位置" % (t["name"], len(t["players"])))
            continue
        slots = ",".join(("null" if p is None else '"%s"' % p) for p in t["players"])
        lines.append('  {name:"%s", region:"%s", players:[%s]},\n'
                     % (t["name"], t.get("region", "NA"), slots))
        have.add(t["name"])
    if not lines:
        return html, skipped, bad
    i = html.index("const OPP_TEAMS")
    j = html.index("\n];", i)
    head = html[:j]
    if not head.rstrip().endswith(","):
        head = head.rstrip() + ","
    return head + "\n" + "".join(lines).rstrip("\n") + html[j:], skipped, bad


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    as_teams = "--teams" in sys.argv
    html = load(HTML)
    data = json.loads(io.open(src, encoding="utf-8-sig").read())
    if as_teams:
        html, skipped, bad = add_teams(html, data)
    else:
        html, skipped, bad = add_cards(html, data)
    io.open(HTML, "w", encoding="utf-8", newline="\n").write(html)
    print("写入 %d 条" % (len(data) - len(skipped) - len(bad)))
    if skipped:
        print("跳过:", "、".join(skipped))
    if bad:
        print("有问题(未写入):")
        for b in bad:
            print("  -", b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
