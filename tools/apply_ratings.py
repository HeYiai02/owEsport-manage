# -*- coding: utf-8 -*-
"""把 data/owl/ratings.json 写回 owcs-manager.html 的 BASE_PLAYERS(四维 + 招牌英雄),
并生成 const RATING_SRC 供卡片/详情显示数据来源。

· 有 OWL 数据的卡:四维与招牌英雄都用数据(英雄 = 打满 60 分钟里时间最长的几个)
· 没有的卡(2025/26 新人):保留手打分,整体平移使中位数与数据卡一致,标"估算"
"""
import io, os, sys, json, re, statistics as st

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HTML = r"E:\code\wishingWell\owcs-manager.html"
D = r"E:\code\wishingWell\data\owl"

W_ROLE = {"tank": (.30, .35, .15, .20), "dps": (.45, .20, .20, .15), "sup": (.20, .35, .25, .20)}
HERO_ALIAS = {"mccree": "cassidy"}


def fold(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def overall_of(role, m, q, p, t):
    a, b, c, d = W_ROLE[role]
    return round(a * m + b * q + c * p + d * t)


def parse_calls(body):
    """切出每个 P(...) 调用的文本区间(括号配平,跳过字符串内的括号)。"""
    out, i = [], 0
    while True:
        j = body.find('P("', i)
        if j < 0:
            break
        k, depth, instr, esc = j + 1, 0, False, False
        while k < len(body):
            ch = body[k]
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
            else:
                if ch == '"':
                    instr = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
            k += 1
        out.append((j, k + 1))
        i = k + 1
    return out


def main():
    src = io.open(HTML, encoding="utf-8").read()
    i0 = src.index("const BASE_PLAYERS = [")
    i1 = src.index("let P_CARDS")
    body = src[i0:i1]

    ratings = json.load(io.open(os.path.join(D, "ratings.json"), encoding="utf-8"))
    spans = parse_calls(body)

    cards = []
    for a, b in spans:
        text = body[a:b]
        m = re.match(r'P\("([^"]+)",(\d{4}),"(tank|dps|sup)",(\d+),(\d+),(\d+),(\d+),\[([^\]]*)\]', text)
        if not m:
            print("SKIP", text[:60])
            continue
        cards.append(dict(name=m.group(1), season=int(m.group(2)), role=m.group(3),
                          mech=int(m.group(4)), iq=int(m.group(5)), pool=int(m.group(6)), mental=int(m.group(7)),
                          heroes=[h.strip().strip('"') for h in m.group(8).split(",") if h.strip()],
                          a=a, b=b, text=text))

    dat = [c for c in cards if "%s|%d" % (fold(c["name"]), c["season"]) in ratings]
    est = [c for c in cards if c not in dat]
    med_d = st.median([ratings["%s|%d" % (fold(c["name"]), c["season"])]["overall"] for c in dat])
    med_e = st.median([overall_of(c["role"], c["mech"], c["iq"], c["pool"], c["mental"]) for c in est])
    shift = int(round(med_d - med_e))
    print("数据卡 %d 张(中位 %d),估算卡 %d 张(中位 %d)→ 平移 %+d" % (len(dat), med_d, len(est), med_e, shift))

    srcmap, rebuilt, last = {}, [], 0
    for c in cards:
        k = "%s|%d" % (fold(c["name"]), c["season"])
        if k in ratings:
            r = ratings[k]
            mech, iq, pool, mental = r["mech"], r["iq"], r["pool"], r["mental"]
            heroes = r["heroes"]
            note = r["src"] + ("(样本少)" if r["low"] else "")
        else:
            mech = max(60, min(94, c["mech"] + shift))
            iq = max(60, min(94, c["iq"] + shift))
            pool, mental = c["pool"], max(60, min(94, c["mental"] + shift))
            heroes = c["heroes"]
            note = "无公开数据 · 按队伍水平估算"
        srcmap["%s@%d" % (c["name"], c["season"])] = note
        # 保留原来的 note 字段(在 heroes 数组之后)
        tail = c["text"]
        ti = tail.index("]", tail.index("[")) + 1
        rest = tail[ti:]
        herostr = ",".join('"%s"' % h for h in heroes)
        rebuilt.append(body[last:c["a"]])
        rebuilt.append('P("%s",%d,"%s",%d,%d,%d,%d,[%s]%s'
                       % (c["name"], c["season"], c["role"], mech, iq, pool, mental, herostr, rest))
        last = c["b"]
    rebuilt.append(body[last:])
    body2 = "".join(rebuilt)
    src = src[:i0] + body2 + src[i1:]

    js = "const RATING_SRC = " + json.dumps(srcmap, ensure_ascii=False, indent=0) + ";\n"
    if "const RATING_SRC =" in src:
        a = src.index("const RATING_SRC =")
        b = src.index("};\n", a) + 3
        src = src[:a] + js + src[b:]
    else:
        src = src.replace("const BASE_PLAYERS = [", js + "\nconst BASE_PLAYERS = [", 1)

    io.open(HTML, "w", encoding="utf-8", newline="\n").write(src)
    ovs = [ratings["%s|%d" % (fold(c["name"]), c["season"])]["overall"] for c in dat]
    print("写入完成:数据卡综合 %d-%d 中位 %d;估算卡已平移 %+d" % (min(ovs), max(ovs), st.median(ovs), shift))


if __name__ == "__main__":
    main()
