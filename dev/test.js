// 回归测试:在 Node vm 里跑 owcs-manager.html 的主流程(选图 → ban → 体系 → 模拟 → 复盘)
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "..", "owcs-manager.html"), "utf8");
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]);
const main = blocks.filter(b => b.includes("const HEROES")).pop();
const m = main ? [null, main] : null;
if (!m) { console.error("找不到 script 块"); process.exit(1); }

function makeEl(id) {
  const el = {
    id, innerHTML: "", textContent: "", value: "", scrollTop: 0,
    style: {}, className: "", files: [], dataset: {},
    classList: { add() {}, remove() {}, contains() { return false; }, toggle() {} },
    click() {}, focus() {}, appendChild() {}, remove() {},
    querySelector: () => makeEl("q"),
    querySelectorAll: () => [],
  };
  return el;
}
const els = {};
const store = new Map();

const sandbox = {
  console, Date, Math, JSON, isNaN, parseInt, parseFloat, RegExp, Error,
  setTimeout: (fn) => { fn(); return 0; },
  setInterval: () => 0,
  clearInterval: () => {},
  clearTimeout: () => {},
  alert: (s) => console.log("[alert]", s),
  confirm: () => true,
  document: {
    getElementById: (id) => (els[id] = els[id] || makeEl(id)),
    querySelector: () => makeEl("query"),
    createElement: (tag) => makeEl(tag),
    write() {}, close() {},
  },
  localStorage: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  },
  URL: { createObjectURL: () => "blob:x" },
  Blob: function () {},
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.globalThis = sandbox;

const ctx = vm.createContext(sandbox);

try {
  vm.runInContext(m[1], ctx, { filename: "owcs-manager.html<script>" });
} catch (e) {
  console.error("✗ 脚本加载失败:", e.message);
  console.error(e.stack.split("\n").slice(0, 5).join("\n"));
  process.exit(1);
}
console.log("✓ 脚本加载");

const TEST = `
(function(){
  function assert(c, msg){ if(!c) throw new Error(msg); }
  function step(name, fn){
    try { fn(); console.log("✓ " + name); }
    catch(e){ console.log("✗ " + name + " :: " + e.message); FAILED++; }
  }
  var FAILED = 0;

  step("旧存档 / 未知阶段不会白屏", function(){
    ["veto","banorder","weird-phase"].forEach(function(ph){
      try{ localStorage.setItem(LSKEY, JSON.stringify({v:2,S:{phase:ph,teamName:"Old",budget:140,roster:[]},C:null,cards:null})); }catch(e){}
      loadLocal();
      assert(S.phase !== ph, ph + " 没有被回落");
      render();
      assert(app.innerHTML.indexOf("script") < 0, "渲染出现异常");
    });
    hardReset();
  });

  step("英雄数据完整性", function(){
    assert(HEROES.length >= 54, "英雄数 " + HEROES.length);
    var byRole = {};
    HEROES.forEach(function(h){ byRole[h.role] = (byRole[h.role]||0)+1; });
    assert(byRole.tank && byRole.dps && byRole.sup, "位置缺失");
    HEROES.forEach(function(h){
      assert(["dive","brawl","poke"].indexOf(h.arch) >= 0, h.name + " arch 非法: " + h.arch);
    });
    var noImg = HEROES.filter(function(h){ return !heroImg(h.name); }).map(function(h){ return h.name; });
    assert(!noImg.length, "缺头像: " + noImg.join(","));
    console.log("    英雄 " + HEROES.length + " -> " + JSON.stringify(byRole) + " · 头像齐全");
  });

  step("地图分组符合 OWCS 9.4.2", function(){
    var groups = {};
    MAPS.forEach(function(mp){
      var g = MODE_GROUP[mp.mode];
      assert(g, mp.name + " 模式 " + mp.mode + " 无分组");
      groups[g] = (groups[g]||0)+1;
    });
    ["Control","HyFlex","PushClash","Escort"].forEach(function(g){
      assert(groups[g] >= 2, "组 " + g + " 只有 " + (groups[g]||0) + " 张图");
    });
    assert(!MAPS.some(function(mp){ return mp.mode === "Clash"; }), "还有 Clash 地图");
    var noBg = MAPS.filter(function(mp){ return !mapImg(mp.name); }).map(function(mp){ return mp.name; });
    assert(noBg.length <= 2, "缺背景图的太多: " + noBg.join(","));
    console.log("    地图 " + MAPS.length + " -> " + JSON.stringify(groups)
      + " · 有背景图 " + (MAPS.length - noBg.length) + "/" + MAPS.length
      + (noBg.length ? " (" + noBg.join(",") + " 用渐变底)" : ""));
  });

  step("选手卡完整性", function(){
    var names = {}; HEROES.forEach(function(h){ names[h.name] = 1; });
    var bad = [];
    P_CARDS.forEach(function(p){
      if (["tank","dps","sup"].indexOf(p.role) < 0) bad.push(p.name + " 位置 " + p.role);
      if (!p.heroes || !p.heroes.length) bad.push(p.name + " 无英雄");
      (p.heroes || []).forEach(function(h){ if(!names[h]) bad.push(p.name + " 未知英雄 " + h); });
    });
    assert(!bad.length, bad.join(" | "));
    var byRole = {};
    P_CARDS.forEach(function(p){ byRole[p.role] = (byRole[p.role]||0)+1; });
    console.log("    选手 " + P_CARDS.length + " -> " + JSON.stringify(byRole));
  });

  step("建队 -> 选秀 -> 开赛", function(){
    S.teamName = "测试队";
    startDraft();
    assert(S.phase === "draft", "未进入 draft, 实际 " + S.phase);
    for (var guard = 0; guard < 40 && S.roster.length < 5; guard++) {
      var need = roleNeeds();
      var role = Object.keys(need).filter(function(r){ return need[r] > 0; })[0];
      if (!role) throw new Error("roleNeeds 无需求");
      var cand = P_CARDS.filter(function(p){
        return p.role === role && canPick(p);
      }).sort(function(a,b){ return overall(b) - overall(a); })[0];
      if (!cand) throw new Error("没有可选 " + role + " (预算 " + S.budget + ")");
      draftPick(cand.id);
    }
    assert(S.roster.length === 5, "阵容 " + S.roster.length + " 人");
    startSeries();
    S.seedHigh = "me";            // 固定种子顺位, 保证第一张的选图/ban 先后手都归玩家
    assert(S.oppRoster.length === 5, "对手 " + S.oppRoster.length + " 人");
    assert(S.groupsLeft.length === 4, "模式组初始化 " + S.groupsLeft.length);
  });

  step("对手是真实战队, 抢人之后用同位置替补补位", function(){
    assert(typeof S.oppTeam === "string" && S.oppTeam.length, "没有战队名");
    var t = OPP_TEAMS.filter(function(x){ return x.name === S.oppTeam; })[0];
    assert(t, "对手战队不在名单里: " + S.oppTeam);
    var names = S.oppRoster.map(function(p){ return p.name.toLowerCase(); });
    assert(names.length === 5, "对手 " + names.length + " 人");
    assert(new Set(names).size === 5, "对手有重复选手: " + names.join(","));
    var roles = S.oppRoster.map(function(p){ return p.role; }).sort().join(",");
    assert(roles === "dps,dps,sup,sup,tank", "对手位置不对: " + roles);
    var real = t.players.filter(function(k){
      var c = cardByKey(k);
      return c && !S.roster.some(function(r){ return r.name.toLowerCase() === c.name.toLowerCase(); });
    }).length;
    var named = t.players.filter(Boolean).length;
    assert(real >= Math.min(2, named), "战队 " + S.oppTeam + " 只剩 " + real + " 名真实成员");
    console.log("    " + S.oppTeam + " · 真实成员 " + real + "/" + named +
                " · " + S.oppRoster.map(function(p){ return p.name; }).join(" / "));
  });

  // ---- 通用流程驱动 ----
  function autoMapSelect(){
    var g = 0;
    while (S.phase === "mapselect" && g++ < 8) {
      if (S.aiPick) {
        commitMap(S.aiPick.map, S.aiPick.side === "atk" ? "def" : "atk");
      } else if (S.pickFor === "me") {
        var opts = mapOptions(S.pickGroups);
        if (!opts.length) throw new Error("没有任何可选地图组");
        var mp = opts[0].maps[0];
        pickMap(mp.name, "def");
      } else {
        throw new Error("mapselect 卡住 pickFor=" + S.pickFor);
      }
    }
    if (S.phase === "mapselect") throw new Error("选图循环未结束");
  }
  function autoBanOrder(){
    var g = 0;
    while (S.phase === "banorder" && g++ < 4) chooseBanOrder("me");
    if (S.phase === "banorder") throw new Error("banorder 没结束");
  }
  function autoBan(){
    var g = 0;
    while (S.phase === "ban" && g++ < 8) {
      if (nextBanSide() === "me") {
        var cand = HEROES.filter(function(h){ return banLegalFor(h, "me"); });
        if (!cand.length) throw new Error("没有合法 ban");
        doBan(cand[0].name);
      } else {
        aiBan();
      }
    }
    if (S.phase === "ban") throw new Error("ban 循环未结束, 已 ban " + S.bans.length);
  }
  function playOneMap(arch){
    beginMapSelect();
    autoMapSelect();
    assert(S.curMap, "没选到地图");
    assert(S.phase === "ban" || S.phase === "banorder", "选图后未进入 ban, 实际 " + S.phase);
    autoBanOrder();
    autoBan();
    assert(S.phase === "arch", "ban 后未进入 arch, 实际 " + S.phase);
    pickArch(arch || "dive");
    assert(S.curMapResult, "无比赛结果");
    afterMap();
  }

  step("第一张图:固定 Control + 种子顺位高的一方选", function(){
    var first = S.mapSeq.length === 0;
    assert(first, "mapSeq 不为空");
    beginMapSelect();
    assert(S.pickGroups.length === 1 && S.pickGroups[0] === "Control", "第一张不是 Control: " + S.pickGroups);
    autoMapSelect();
    assert(S.curMap.group === "Control", "第一张图组 " + S.curMap.group);
    assert(S.curMap.name, "图名缺失");
    console.log("    第 1 张 " + S.curMap.name + " · 选图方 " + S.mapSeq[0].picker + " · 你" + (S.side.me==="atk"?"进攻":"防守"));
  });

  step("ban 先后手:选图方拥有决定权", function(){
    assert(S.banPriority === S.seedHigh, "banPriority " + S.banPriority + " 不等于 seedHigh " + S.seedHigh);
    assert(S.phase === "banorder", "你拥有决定权时应停在 banorder, 实际 " + S.phase);
    assert(!S.banFirst, "还没选就已有 banFirst");
    chooseBanOrder("me");
    assert(S.banFirst === "me", "选了先 ban 但 banFirst=" + S.banFirst);
    assert(S.phase === "ban", "选完先后手应进入 ban, 实际 " + S.phase);
    console.log("    种子顺位 " + S.seedHigh + " · 停在 banorder · 选择自己先 ban 后进入 ban ✓");
  });

  step("英雄 ban:每队 1 个 + 职责锁 + 全系列赛不重复", function(){
    autoBan();
    assert(S.bans.length === 2, "ban 数 " + S.bans.length);
    var roles = S.bans.map(function(b){ return HERO_BY_NAME[b.hero].role; });
    assert(roles[0] !== roles[1], "两个 ban 撞了同一职责: " + roles.join(","));
    assert(S.bans[0].side !== S.bans[1].side, "两个 ban 来自同一方");
    console.log("    " + S.bans.map(function(b){ return b.hero + "(" + b.side + "/" + HERO_BY_NAME[b.hero].role + ")"; }).join(" "));
  });

  step("选体系 -> 模拟 -> 复盘", function(){
    pickArch("dive");
    var r = S.curMapResult;
    var rule = MODE_RULE[r.mode];
    assert(r.my >= 0 && r.opp >= 0, "比分异常");
    if (rule.kind === "points") {
      assert(r.my === rule.need || r.opp === rule.need, "比分没打到 " + rule.need + ": " + r.my + "-" + r.opp);
      assert(Math.max(r.my, r.opp) === rule.need, "赢家没停在 " + rule.need + ": " + r.my + "-" + r.opp);
    } else if (rule.kind === "payload") {
      assert(Math.max(r.my, r.opp) <= 4, "检查点超出: " + r.my + "-" + r.opp);
    } else {
      assert(r.my <= 150.1 && r.opp <= 150.1, "推车距离异常");
    }
    assert(r.win === (r.my > r.opp), "胜负与比分不一致");
    assert(typeof r.pWin === "number", "缺单图胜率");
    // 事件流:每张图至少 18 句,且每个得分单元至少 4 句
    var lines = S.lines || [];
    assert(lines.length >= 18, "解说太短,只有 " + lines.length + " 句");
    var units = Math.max(1, r.unit === "push" ? 1 : (r.unit === "payload" ? 2 : Math.max(r.my, r.opp)));
    assert(lines.length >= units * 4, "每个得分单元事件太少");
    var withWho = lines.filter(function(l){ return l.pi != null; }).length;
    assert(withWho >= units * 3, "有名字的选手镜头太少");
    console.log("    " + r.map + "(" + r.mode + ") " + r.score + " " + (r.win ? "胜" : "负")
      + " · 规则 " + r.ruleTag + " · 单图胜率 " + r.pWin + "% · 解说 " + lines.length + " 句");
    // E/D 必须由解说里的事件长出来
    var anyEvent = r.myStats.concat(r.oppStats).some(function(s){ return s.elim > 0 && s.death > 0; });
    assert(anyEvent, "复盘里的 E/D 没有来自事件");
    // 被 ban 的英雄不能上场
    var banned = S.bans.map(function(b){ return b.hero; });
    r.myStats.concat(r.oppStats).forEach(function(s){
      assert(banned.indexOf(s.hero) < 0, "被 ban 的 " + s.hero + " 仍被使用");
    });
    // 同一队不能有两人用同一英雄
    [r.myStats, r.oppStats].forEach(function(list){
      var seen = {};
      list.forEach(function(s){
        assert(!seen[s.hero], "同队重复英雄 " + s.hero);
        seen[s.hero] = 1;
      });
    });

    afterMap();
    assert(S.phase === "report", "未进入 report, 实际 " + S.phase);
    assert(S.lastLoser, "未记录败方");
  });

  step("打完整个 BO3(败方选图 + 图不重复)", function(){
    var g = 0;
    while (S.myMaps < 2 && S.oppMaps < 2 && g++ < 8) {
      S.phase = "series"; render();
      playOneMap(["dive","brawl","poke"][g % 3]);
    }
    assert(S.myMaps === 2 || S.oppMaps === 2, "系列赛未结束 " + S.myMaps + "-" + S.oppMaps);
    var used = S.mapSeq.map(function(x){ return x.map; });
    var uniq = used.filter(function(v,i){ return used.indexOf(v) === i; });
    assert(used.length === uniq.length, "同一张图打了两次: " + used.join(","));
    assert(S.seriesBans.length === S.mapSeq.length * 2, "系列赛 ban 账本 " + S.seriesBans.length);
    console.log("    系列赛 " + S.myMaps + "-" + S.oppMaps + " · " + S.mapSeq.length + " 张图 · "
      + used.join(" / "));
  });

  step("Ban 账本约束:同一队不重复 ban 同一英雄", function(){
    var seen = {};
    var bad = [];
    S.seriesBans.forEach(function(b){
      var k = b.side + "|" + b.hero;
      if (seen[k]) bad.push(k);
      seen[k] = 1;
    });
    assert(!bad.length, "重复 ban: " + bad.join(","));
  });

  step("生涯:建队余钱变启动资金, 打赢赛事有奖金", function(){
    enterCareer();
    assert(C && typeof C.money === "number", "生涯状态没建起来");
    assert(C.money === Math.max(0, S.budget), "启动资金 " + C.money + " 不等于剩余预算 " + S.budget);
    assert(S.phase === "career", "没进入生涯页 " + S.phase);
    assert(evUnlocked(EVENTS[0]), "第一站没解锁");
    assert(!evUnlocked(EVENTS[2]), "第三站不该解锁");

    var money0 = C.money;
    careerStart("t3a");
    assert(C.cur && C.cur.eventId === "t3a" && C.cur.round === 1, "没开始赛事");
    assert(C.money === money0 - evById("t3a").entry, "报名费没扣: " + C.money);
    assert(S.phase === "series", "没进入系列赛 " + S.phase);

    var g = 0;
    while (S.myMaps < 2 && S.oppMaps < 2 && g++ < 8) {
      S.phase = "series"; render();
      playOneMap("dive");
    }
    var won = S.myMaps > S.oppMaps;
    var before = C.money;
    finishCareerSeries();
    assert(S.phase === "career", "结算后没回生涯 " + S.phase);
    if (won) {
      assert(C.money > before, "赢了没拿奖金 " + before + " -> " + C.money);
      assert(C.log.length > 0 && C.log[0].k === "w", "日志没记胜场");
    } else {
      assert(C.cur === null, "输了应该结束这次报名");
      assert(C.log.length > 0 && C.log[0].k === "l", "日志没记败场");
    }
    console.log("    " + (won ? "赢" : "输") + " · 资金 " + money0 + " -> " + C.money
      + " · 周 " + C.week + " · 冠军 " + Object.keys(C.cleared).length);
  });

  step("赌场:押注扣钱, 结算不吞钱, 豹子通杀", function(){
    C.money = 500;
    openCasino();
    assert(S.phase === "casino", "没进赌场");
    var before = C.money;
    CAS.bet = 20; CAS.type = "big";
    casinoRoll();
    var after = C.money;
    assert(after === before - 20 || after === before + 20, "押 20 结算异常 " + before + " -> " + after);
    assert(CAS.last && typeof CAS.last.win === "boolean", "没有结算结果");
    assert(C.casino.n === 1, "局数没记");

    // 豹子:三颗一样时押大的输、押豹子的赢(本金在掷骰前已扣, 这里手动模拟)
    CAS.dice = [4,4,4]; CAS.type = "big"; C.money = 100 - 10;
    settleCasino(10);
    assert(C.money === 90, "豹子押大应该输掉本金 " + C.money);
    CAS.dice = [4,4,4]; CAS.type = "leopard"; C.money = 100 - 10;
    settleCasino(10);
    assert(C.money === 180, "豹子押中应该 8 倍返还 " + C.money);
    console.log("    赌场结算正常 · 豹子 8 倍");
    closeCasino();
    assert(S.phase === "career", "没回到生涯");
  });

  step("存档结构与恢复", function(){
    // 先打一张图, 让存档落在一个"打到一半"的阶段
    S.phase = "series"; render();
    playOneMap("dive");
    assert(S.phase === "report", "打一张图后应停在 report, 实际 " + S.phase);
    var raw = localStorage.getItem(LSKEY);
    assert(raw, "未写存档");
    var d = JSON.parse(raw);
    assert(d.v === 2 && d.S && d.cards, "存档结构不全");
    assert("C" in d, "存档缺生涯状态字段");
    console.log("    存档 " + Math.round(raw.length/1024) + "KB, 阶段 " + d.S.phase);
    var ok = loadLocal();
    assert(ok === true, "loadLocal 返回 " + ok);
    assert(d.S.phase === "report" || d.S.phase === "done", "意外阶段 " + d.S.phase);
  });

  step("数据编辑 applyCards", function(){
    var backup = JSON.parse(JSON.stringify(P_CARDS));
    var edited = JSON.parse(JSON.stringify(P_CARDS));
    edited[0].mech = 99;
    applyCards(edited);
    assert(P_CARDS[0].mech === 99, "applyCards 未生效");
    assert(P_CARDS[0].id, "applyCards 丢了 id");
    applyCards(backup);
    assert(P_CARDS[0].mech === backup[0].mech, "恢复失败");
  });

  step("重开清空状态", function(){
    hardReset();
    assert(S.phase === "setup", "重开阶段 " + S.phase);
    assert(S.mapSeq.length === 0 && S.seriesBans.length === 0, "重开未清空");
  });

  return FAILED;
})();
`;

let failed = 1;
try {
  failed = vm.runInContext(TEST, ctx, { filename: "test.js" });
} catch (e) {
  console.error("✗ 测试中断:", e.message);
  console.error(e.stack.split("\n").slice(0, 6).join("\n"));
  process.exit(1);
}
console.log(failed ? "\n结果: " + failed + " 项失败" : "\n结果: 全部通过");
process.exit(failed ? 1 : 0);
